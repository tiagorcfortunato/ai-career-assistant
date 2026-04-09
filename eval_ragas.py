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
from langchain_groq import ChatGroq
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
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# ── Test dataset: questions + ground truth references ──────────────────────

TEST_CASES = [
    {
        "question": "What projects has Tiago built?",
        "reference": "Tiago has built three main projects: (1) Odys, a WhatsApp-first scheduling SaaS for freelance professionals in Brazil, built entirely solo; (2) A RAG Career Chatbot with streaming SSE, section-aware chunking, and local embeddings deployed on Render; (3) An Inspection Management API with AI-powered damage classification using Groq Llama 3.2 11B Vision, JWT auth, admin roles, and 31 Pytest tests.",
    },
    {
        "question": "What is his AI and ML experience?",
        "reference": "Tiago has experience with RAG pipelines (LangChain, ChromaDB, fastembed), LLM integration (Groq API, structured output), multimodal AI classification (Llama 3.2 11B Vision for road damage images), YOLOv8 object detection for his MSc thesis on road surface hazard detection, and prompt engineering for production systems.",
    },
    {
        "question": "Tell me about his MSc thesis",
        "reference": "Tiago's MSc thesis is titled 'Expert System for Road Surface Hazard Detection'. It presents a modular two-component pipeline: a YOLOv8 object detection model identifies road defects from images, and a deterministic rule-based expert system assigns maintenance priority levels (Low/Medium/High). Best result: mAP50 of 0.663 with YOLOv8s. Post-processing reduced noisy detections by 31.2%. Submitted February 2026 at University of Europe for Applied Sciences, Berlin.",
    },
    {
        "question": "How would he turn an API into a developer platform?",
        "reference": "First talk to early adopters to understand friction. Then focus on three areas: (1) API design — clear versioning, predictable response structures, meaningful error handling; (2) Developer experience — documentation based on real workflows, not just endpoints; (3) Reliability — rate limiting, monitoring, clear latency/uptime expectations.",
    },
    {
        "question": "Show me code examples from the Inspection API",
        "reference": "The Inspection API has several key code patterns: AI classification service with vision and text paths using Groq SDK, background AI processing with FastAPI BackgroundTask, override tracking with SQLAlchemy hybrid_property, and 31 integration tests. Code is at github.com/tiagorcfortunato/inspection-management-api.",
    },
    {
        "question": "Tell me about Odys",
        "reference": "Odys is a WhatsApp-first SaaS platform built entirely solo for Brazilian freelance professionals. It features self-service booking pages, automated WhatsApp reminders from the professional's own number via self-hosted Evolution API, Stripe payments with PIX, multi-tenant architecture, and Supabase pg_cron for scheduled tasks. It's live in production but Tiago hasn't focused on distribution yet.",
    },
    {
        "question": "What would he do in his first 30 days at a new company?",
        "reference": "Understanding before building, but not passively. Go deep into the existing system, current API, and how it's being used — run it locally, explore edge cases, try to break it from a developer's perspective. In parallel, talk to users to understand where the interface creates friction. Identify one or two high-impact improvements and start implementing before end of first month.",
    },
    {
        "question": "How many users does Odys have?",
        "reference": "Odys is live in production but Tiago hasn't focused on distribution yet, so there is no meaningful user traction to claim. His priority has been building the product and validating core workflows technically before pushing for growth.",
    },
    {
        "question": "What are the limitations of RAG systems?",
        "reference": "Four main limitations: (1) Retrieval quality — if relevant context isn't retrieved, the answer fails; (2) Hallucinations — even with right context, the model can generate incorrect responses; (3) Latency and cost at scale; (4) Evaluation is hard without labeled ground truth.",
    },
    {
        "question": "What does founder-level ownership mean to him?",
        "reference": "It means not waiting to be told where the problem is. Understanding the user, identifying what matters most, making decisions with incomplete information, and taking responsibility for the outcome — not just the implementation. Thinking beyond the code and treating the product as something you are fully accountable for.",
    },
]


def get_rag_response(question: str) -> dict:
    """Query the live chatbot API and return answer + retrieved contexts."""
    res = httpx.post(
        f"{API_URL}/api/query",
        json={"question": question, "document_id": None, "history": []},
        timeout=30,
    )
    res.raise_for_status()
    data = res.json()
    return {
        "answer": data["answer"],
        "contexts": [s["content"] for s in data.get("sources", [])],
    }


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

    # 1. Set up evaluator LLM (Groq as the judge) and embeddings (local fastembed)
    evaluator_llm = LangchainLLMWrapper(
        ChatGroq(model="llama-3.1-8b-instant", api_key=GROQ_API_KEY)
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
