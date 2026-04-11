import os
import sys
import asyncio
from dotenv import load_dotenv
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
import mcp.types as types

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_postgres import PGVector
from langchain_openai import ChatOpenAI
from langchain_classic.chains import create_retrieval_chain
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate

load_dotenv()

connection_string = os.getenv("VECTOR_DATABASE_URL")
if not connection_string:
    raise ValueError("VECTOR_DATABASE_URL tidak ditemukan di file .env")

API_KEY = os.getenv("OPENROUTER_API_KEY")
BASE_URL = os.getenv("OPENROUTER_BASE_URL")

# Inisialisasi model dan vectorstore
embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2",
    model_kwargs={'device': 'cpu'},
    encode_kwargs={'normalize_embeddings': False}
)

COLLECTION_NAME = "permenpan_index_v3" 
vectorstore = PGVector(
    embeddings=embeddings,
    collection_name=COLLECTION_NAME,
    connection=connection_string,
    use_jsonb=True,
)

llm = ChatOpenAI(
    model="arcee-ai/trinity-large-preview:free", 
    api_key=API_KEY,
    base_url=BASE_URL,
    temperature=0
)

retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

system_prompt = (
    "Anda adalah asisten AI yang membantu menjawab pertanyaan berdasarkan konteks yang diberikan di bawah ini. "
    "Jika jawaban tidak ada di dalam konteks, katakan 'Saya tidak menemukan informasi tersebut di dokumen'. "
    "Jawablah dengan bahasa Indonesia yang jelas.\n\n"
    "Konteks:\n{context}"
)

prompt = ChatPromptTemplate.from_messages([
    ("system", system_prompt),
    ("human", "{input}"),
])

question_answer_chain = create_stuff_documents_chain(llm, prompt)
rag_chain = create_retrieval_chain(retriever, question_answer_chain)

# Inisialisasi MCP Server
app = Server("pdf-rag-server")

@app.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """Menampilkan tool yang tersedia di MCP Server ini."""
    return [
        types.Tool(
            name="query_pdf",
            description="Mencari dan menjawab pertanyaan dari dokumen PDF yang telah diindeks di database.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Pertanyaan mengenai isi dokumen PDF."
                    },
                },
                "required": ["query"],
            },
        )
    ]

@app.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Menangani pemanggilan tool."""
    if name == "query_pdf":
        query = arguments.get("query")
        if not query:
            raise ValueError("Parameter 'query' dibutuhkan")
        
        try:
            response = rag_chain.invoke({"input": query})
            answer = response["answer"]
            
            # Format sumber referensi jika diperlukan
            sources = "\n\nSumber Referensi:\n"
            for i, doc in enumerate(response["context"]):
                sources += f"[{i+1}] Halaman {doc.metadata.get('page', '?')}\n"
                
            return [
                types.TextContent(
                    type="text",
                    text=answer + sources
                )
            ]
        except Exception as e:
            raise ValueError(f"Error saat mencari dokumen: {str(e)}")
    
    raise ValueError(f"Tool tidak dikenali: {name}")

async def main():
    # Menjalankan server menggunakan stdio (standar input/output pipes)
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="pdf-rag-server",
                server_version="0.1.0",
                capabilities=app.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    # Karena MCP menggunakan stdout untuk komunikasi, matikan print yang mungkin merusak JSON format.
    asyncio.run(main())
