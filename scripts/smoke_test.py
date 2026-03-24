#!/usr/bin/env python3
"""
Medical Agentic RAG – Quick Reference & Testing Script
=====================================================
Helps you test the system quickly without manual API calls.
"""

import requests
import json
import time

API_BASE = "http://localhost:8000"

def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")

def test_health():
    """Test backend health."""
    print_header("Testing Backend Health")
    try:
        res = requests.get(f"{API_BASE}/api/health")
        if res.ok:
            data = res.json()
            print("✅ Backend is HEALTHY")
            print(f"   Version: {data['version']}")
            print(f"   LLM: {data['models']['llm']}")
            print(f"   Embeddings: {data['models']['embeddings']}")
            print(f"   Q&A Records: {data['databases']['qa_collection_count']}")
            print(f"   Device Records: {data['databases']['device_collection_count']}")
            return True
        else:
            print("❌ Backend returned error:", res.status_code)
            return False
    except Exception as e:
        print(f"❌ Cannot connect to backend at {API_BASE}")
        print(f"   Error: {str(e)}")
        print(f"\n   💡 Make sure backend is running:")
        print(f"      ./start_backend.sh")
        return False

def test_query(query, sample=False):
    """Test a medical query."""
    print_header(f"Testing Query: '{query}'")
    try:
        res = requests.post(
            f"{API_BASE}/api/query",
            json={"query": query},
            timeout=30
        )
        
        if res.ok:
            data = res.json()
            print(f"✅ Query successful (took {time.time():.1f}s)")
            print(f"\n📍 Source: {data['source']}")
            print(f"   📌 Routing: {data['source_info']['routing']}")
            print(f"   💬 Reason: {data['source_info']['reason']}")
            print(f"\n✓ Relevant: {data['relevance']['is_relevant']}")
            print(f"\n📝 Answer:\n   {data['answer']}")
            print(f"\n🔍 Context (first 200 chars):\n   {data['context']}")
            print(f"\n📊 Iterations: {data['iteration_count']}")
            print(f"⏰ Timestamp: {data['timestamp']}")
            return True
        else:
            print(f"❌ Query failed: {res.status_code}")
            print(f"   {res.json()}")
            return False
    except requests.exceptions.Timeout:
        print("❌ Query timed out (30s). Backend might be slow.")
        return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

def test_ingest():
    """Test data ingestion."""
    print_header("Testing Data Ingestion")
    try:
        res = requests.post(
            f"{API_BASE}/api/ingest",
            json={"qa_csv": "medical_q_n_a.csv", "sample_size": 10},
            timeout=60
        )
        
        if res.ok:
            data = res.json()
            print(f"✅ Data ingestion successful")
            print(f"   Q&A Records: {data['qa_records']}")
            print(f"   Device Records: {data['device_records']}")
            return True
        else:
            print(f"❌ Ingestion failed: {res.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

def sample_questions():
    """Test with sample medical questions."""
    questions = [
        "What are symptoms of diabetes?",
        "What is hypertension?",
        "How do pacemakers work?",
        "What are contraindications for antibiotics?",
        "Latest COVID-19 treatments?",
    ]
    
    print_header("Testing Sample Queries")
    print("Testing 3 sample questions...\n")
    
    for i, q in enumerate(questions[:3], 1):
        print(f"{i}. Testing: {q}")
        if test_query(q):
            print("   ✅ Success\n")
        else:
            print("   ❌ Failed\n")
            break

def interactive():
    """Interactive query mode."""
    print_header("Interactive Mode")
    print("Ask medical questions (type 'quit' to exit)\n")
    
    while True:
        query = input("🏥 Ask: ").strip()
        if query.lower() == 'quit':
            print("\n👋 Goodbye!")
            break
        if not query:
            continue
        
        test_query(query)

def main():
    """Main testing menu."""
    print("\n")
    print("  🏥 Medical Agentic RAG – Quick Test Suite")
    print("  ==========================================\n")
    
    while True:
        print("\nChoose an option:")
        print("  1. Check backend health")
        print("  2. Test sample queries")
        print("  3. Test custom query")
        print("  4. Test data ingestion")
        print("  5. Interactive mode")
        print("  6. Exit")
        print()
        
        choice = input("Your choice (1-6): ").strip()
        
        if choice == "1":
            if not test_health():
                input("\nPress Enter to continue...")
        
        elif choice == "2":
            sample_questions()
        
        elif choice == "3":
            query = input("\n🏥 Enter your question: ").strip()
            if query:
                test_query(query)
        
        elif choice == "4":
            if test_health():
                test_ingest()
        
        elif choice == "5":
            if test_health():
                interactive()
        
        elif choice == "6":
            print("\n👋 Goodbye!")
            break
        
        else:
            print("❌ Invalid choice")

if __name__ == "__main__":
    main()
