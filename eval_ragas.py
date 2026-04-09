"""
RAGAS Evaluation Script for the Career Chatbot RAG Pipeline.

Queries the live chatbot API, collects answers + retrieved contexts,
then evaluates with RAGAS metrics:
  - Faithfulness: Are factual claims grounded in retrieved context?
  - Answer Relevancy: Does the answer address the question?
  - Context Precision: Are retrieved chunks relevant?
  - Context Recall: Were the right chunks retrieved?
"""

import os
import json
import httpx
from dotenv import load_dotenv

load_dotenv()

from ragas import evaluate, EvaluationDataset, SingleTurnSample
from ragas.metrics import Faithfulness, AnswerRelevancy, ContextPrecision, ContextRecall
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from langchain_google_genai import ChatGoogleGenerativeAI
from fastembed import TextEmbedding
from langchain_core.embeddings import Embeddings


class FastEmbeddings(Embeddings):
    def __init__(self):
        self._model = TextEmbedding("BAAI/bge-small-en-v1.5")

    def embed_documents(self, texts):
        return [e.tolist() for e in self._model.embed(texts)]

    def embed_query(self, text):
        return list(self._model.embed([text]))[0].tolist()

# ── Config ─────────────────────────────────────────────────────────────────

API_URL = os.getenv("EVAL_API_URL", "https://chatbot.tifortunato.com")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# ── Test dataset: questions + ground truth references ──────────────────────

TEST_CASES = [
    {
        "question": "What projects has Tiago built?",
        "reference": "Tiago has built three main projects: (1) RAG Career Chatbot — AI career assistant with streaming SSE, LangChain, ChromaDB, Groq, deployed on Render. (2) Inspection Management API — REST API with AI-powered damage classification using Groq Llama 3.2 11B Vision, JWT auth, admin roles, 31 Pytest tests. (3) Odys — WhatsApp-first scheduling SaaS built entirely solo, live at odys.com.br, with Stripe payments and self-hosted WhatsApp API.",
    },
    {
        "question": "What is his AI and ML experience?",
        "reference": "Tiago has experience with RAG (Retrieval-Augmented Generation) — end-to-end pipeline design and implementation. LangChain — orchestration, prompt templates, message history, chains. ChromaDB — vector store, persistent embeddings, metadata filtering. fastembed — local embedding model inference (BAAI/bge-small-en-v1.5). Groq API — LLM inference (Llama 3.1 8B). YOLOv8 (Ultralytics) — object detection, training, evaluation (mAP, precision, recall). PyTorch — model training, GPU-accelerated inference. Scikit-learn — classical ML, evaluation metrics. Claude Code — AI-assisted development workflow.",
    },
    {
        "question": "Tell me about his MSc thesis",
        "reference": "Tiago's MSc thesis is titled 'Expert System for Road Surface Hazard Detection: A Deep Learning-Based Detection and Maintenance Prioritization Pipeline', submitted in February 2026 at the University of Europe for Applied Sciences, Berlin. It presents a modular two-component pipeline: a YOLOv8 object detection model identifies road surface defects (potholes, cracks) from monocular images, and a deterministic rule-based expert system assigns maintenance priority levels (Low / Medium / High) based on defect type, confidence scores, and detection count. Best result: mAP50 of 0.663 with YOLOv8s, with post-processing reducing noisy detections by 31.2%. The architecture separates perception from reasoning, allowing decision logic to be updated without retraining the model.",
    },
    {
        "question": "How would he turn an API into a developer platform?",
        "reference": "First, talk to early adopters to understand friction. Then focus on three areas: (1) API design — clear versioning, predictable response structures, meaningful error handling; (2) Developer experience — documentation based on real workflows, not just endpoints; (3) Reliability — rate limiting, monitoring, clear latency/uptime expectations.",
    },
    {
        "question": "Show me code examples from the Inspection API",
        "reference": "The Inspection API has several key code patterns: AI classification service with vision and text paths — vision path uses Groq SDK directly because LangChain's wrapper doesn't properly forward base64 images, text path uses LangChain structured output for type-safe enum results. Background AI processing with FastAPI BackgroundTask — API returns immediately (201 status) while AI classification runs in the background. Override tracking with SQLAlchemy hybrid_property — stores both original AI classification and current human-edited values. 31 integration tests running against a real PostgreSQL database in GitHub Actions CI. Code is at github.com/tiagorcfortunato/inspection-management-api.",
    },
    {
        "question": "Tell me about Odys",
        "reference": "Odys is a WhatsApp-first SaaS platform built entirely solo — from architecture to production — targeting Brazilian freelance professionals (psychologists, personal trainers, beauty professionals) who manage appointments manually via WhatsApp. Key features include public booking pages at /p/[slug] with real-time availability, automatic WhatsApp reminders sent 24h before appointments via self-hosted Evolution API v2 running on Railway, Stripe payments with PIX, multi-tenant architecture, and Supabase pg_cron for scheduled tasks. Tech stack: Next.js 16, TypeScript, Supabase, Drizzle ORM, Tailwind CSS + shadcn/ui. Live at odys.com.br.",
    },
    {
        "question": "What would he do in his first 30 days at a new company?",
        "reference": "Understanding before building, but not passively. Go deep into the existing system, the current API, and how it's being used — run it locally, explore edge cases, try to break it from a developer's perspective. In parallel, talk to users to understand where the interface creates friction. Then identify one or two high-impact improvements and start implementing before the end of the first month.",
    },
    {
        "question": "What is his tech stack?",
        "reference": "Backend: Python, FastAPI, PostgreSQL, SQLAlchemy, Drizzle ORM, Pydantic, Alembic, JWT, Pytest. AI & ML: RAG (Retrieval-Augmented Generation), LangChain, ChromaDB, Vector Search, fastembed (BAAI/bge-small-en-v1.5), Groq API (Llama 3.1 8B), YOLOv8 (Ultralytics), PyTorch, Scikit-learn, Pandas, PyMuPDF (fitz). Full-Stack & SaaS: TypeScript, Next.js 16 (App Router), Supabase, Stripe, Resend, Upstash Redis, Evolution API v2, Tailwind CSS + shadcn/ui. DevOps: Docker, GitHub Actions, Vercel, Railway, Render, Git.",
    },
    {
        "question": "What are the limitations of RAG systems?",
        "reference": "Four main ones: (1) Retrieval quality — if the relevant context isn't retrieved, the answer fails regardless of the model; (2) Hallucinations — even with the right context, the model can generate incorrect responses; (3) Latency and cost — combining retrieval and generation adds overhead at scale; (4) Evaluation is hard — it's not always obvious how to measure whether retrieval is improving.",
    },
    {
        "question": "What does founder-level ownership mean to him?",
        "reference": "It means not waiting to be told where the problem is. Understanding the user, identifying what matters most, making decisions with incomplete information, and taking responsibility for the outcome — not just the implementation. Thinking beyond the code and treating the product as something you are fully accountable for.",
    },
]


def get_rag_response(question: str, retries: int = 3) -> dict:
    """Query the live chatbot API and return answer + retrieved contexts."""
    import time
    for attempt in range(retries):
        try:
            res = httpx.post(
                f"{API_URL}/api/query",
                json={"question": question, "document_id": None, "history": []},
                timeout=60,
            )
            res.raise_for_status()
            data = res.json()
            time.sleep(8)  # respect Groq rate limits
            return {
                "answer": data["answer"],
                "contexts": [s["content"] for s in data.get("sources", [])],
            }
        except (httpx.ReadTimeout, httpx.HTTPStatusError) as e:
            print(f"    Retry {attempt+1}/{retries}: {e}")
            time.sleep(15)
    raise RuntimeError(f"Failed after {retries} retries: {question}")


def build_evaluation_dataset() -> EvaluationDataset:
    """Run all test questions through the RAG pipeline and build RAGAS dataset."""
    samples = []

    for i, tc in enumerate(TEST_CASES):
        print(f"  [{i+1}/{len(TEST_CASES)}] {tc['question'][:55]}...")
        result = get_rag_response(tc["question"])

        samples.append(
            SingleTurnSample(
                user_input=tc["question"],
                response=result["answer"],
                retrieved_contexts=result["contexts"],
                reference=tc["reference"],
            )
        )

    return EvaluationDataset(samples=samples)


def main():
    print("\n=== RAGAS Evaluation for Career Chatbot ===")
    print(f"    API: {API_URL}\n")

    # 1. Set up evaluator LLM (Gemini as the judge) and embeddings (local fastembed)
    evaluator_llm = LangchainLLMWrapper(
        ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=GOOGLE_API_KEY)
    )
    evaluator_embeddings = LangchainEmbeddingsWrapper(FastEmbeddings())

    # 2. Run questions through live RAG pipeline
    print("Running questions through RAG pipeline...")
    dataset = build_evaluation_dataset()
    print()

    # 3. Evaluate with RAGAS
    print("Evaluating with RAGAS metrics...\n")
    metrics = [
        Faithfulness(llm=evaluator_llm),
        AnswerRelevancy(llm=evaluator_llm, embeddings=evaluator_embeddings),
        ContextPrecision(llm=evaluator_llm),
        ContextRecall(llm=evaluator_llm),
    ]

    results = evaluate(
        dataset=dataset,
        metrics=metrics,
        llm=evaluator_llm,
        embeddings=evaluator_embeddings,
    )

    # 4. Print results
    df = results.to_pandas()

    print("=" * 55)
    print("          RAGAS EVALUATION RESULTS")
    print("=" * 55)

    for metric_name in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]:
        if metric_name in df.columns:
            avg = df[metric_name].mean()
            print(f"  {metric_name:<25} {avg:.3f}")

    print("-" * 55)

    overall_cols = [c for c in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"] if c in df.columns]
    if overall_cols:
        overall = df[overall_cols].mean().mean()
        print(f"  {'OVERALL':<25} {overall:.3f}")

    print("=" * 55)

    # 5. Per-question breakdown
    print("\nPer-question breakdown:")
    print("-" * 90)
    print(f"  {'Question':<45} {'Faith':>7} {'Relev':>7} {'CPrec':>7} {'CRecl':>7}")
    print("-" * 90)

    for i, row in df.iterrows():
        q = TEST_CASES[i]["question"][:43]
        vals = []
        for m in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]:
            v = row.get(m, None)
            vals.append(f"{v:.2f}" if isinstance(v, (int, float)) and v == v else "  N/A")
        print(f"  {q:<45} {vals[0]:>7} {vals[1]:>7} {vals[2]:>7} {vals[3]:>7}")

    print()

    # 6. Save results
    df.to_csv("ragas_results.csv", index=False)
    print("Full results saved to ragas_results.csv\n")


if __name__ == "__main__":
    main()
