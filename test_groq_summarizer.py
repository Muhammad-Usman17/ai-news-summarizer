#!/usr/bin/env python3
"""
Test script for the new Groq-based summarizer.
This will test the summarizer with mock data without requiring the full workflow.
"""

import asyncio
import os
import sys

# Add the app directory to Python path
sys.path.append('/Users/muhammadusman/Projects/Learning/python/ai-news-summarizer')

from app.agents.summarizer_agent import SummarizerAgent


async def test_groq_summarizer():
    """Test the Groq-based summarizer with sample data."""
    
    print("🚀 Testing Groq-based Summarizer Agent")
    print("=" * 50)
    
    # Mock job ID
    job_id = "test-job-123"
    
    # Sample tech articles for testing
    sample_articles = [
        {
            "title": "Apple Announces New M4 MacBook Pro with Enhanced AI Capabilities",
            "content": "Apple today unveiled its latest MacBook Pro lineup featuring the new M4 chip, which includes significant improvements in AI processing capabilities. The new chip delivers up to 40% faster CPU performance and 50% faster GPU performance compared to the previous M3 generation. The enhanced Neural Engine can process machine learning tasks up to 3x faster, making it ideal for AI development and creative workflows.",
            "url": "https://example.com/apple-m4-macbook",
            "source": "Test Source"
        },
        {
            "title": "OpenAI Releases GPT-5 with Breakthrough Reasoning Capabilities", 
            "content": "OpenAI has announced the release of GPT-5, their most advanced language model to date. The new model demonstrates unprecedented reasoning capabilities, scoring 95% on complex mathematical problems and showing human-level performance on scientific reasoning tasks. The model also features improved factual accuracy and reduced hallucinations compared to previous versions.",
            "url": "https://example.com/openai-gpt5",
            "source": "Test Source"
        }
    ]
    
    try:
        # Check if Groq API key is set
        groq_api_key = os.getenv("GROQ_API_KEY", "")
        if not groq_api_key or groq_api_key == "please_add_your_groq_api_key_here":
            print("❌ GROQ_API_KEY not set!")
            print("Please:")
            print("1. Visit https://console.groq.com/keys")
            print("2. Create an account and generate an API key")
            print("3. Add it to your .env file: GROQ_API_KEY=your_actual_key")
            print("4. Restart this test")
            return False
        
        print(f"✅ Groq API key configured (ending in ...{groq_api_key[-8:]})")
        
        # Create summarizer agent
        summarizer = SummarizerAgent(job_id=job_id)
        
        # Test Groq client health
        print("🔍 Testing Groq API connection...")
        is_healthy = await summarizer.groq_client.check_health()
        
        if not is_healthy:
            print("❌ Groq API connection failed")
            return False
        
        print("✅ Groq API connection successful")
        
        # Test fast summarization
        print(f"\n📝 Testing fast summarization of {len(sample_articles)} articles...")
        
        start_time = asyncio.get_event_loop().time()
        
        # Run the optimized summarizer
        result = await summarizer.run(sample_articles)
        
        end_time = asyncio.get_event_loop().time()
        total_time = end_time - start_time
        
        print(f"⚡ Summarization completed in {total_time:.2f} seconds!")
        print(f"📊 Results: {result['success_count']}/{len(sample_articles)} articles processed")
        
        # Display summaries
        if result['summaries']:
            print("\n📖 Generated Summaries:")
            print("-" * 50)
            
            for i, summary in enumerate(result['summaries'][:2]):  # Show first 2
                print(f"\n{i+1}. {summary['article_title'][:60]}...")
                print(f"   Summary: {summary['summary']}")
                print(f"   Key Points:")
                for point in summary['bullet_points'][:3]:
                    print(f"   • {point}")
                print(f"   Processing Time: {summary['processing_time']:.2f}s")
        
        avg_time = total_time / len(sample_articles) if sample_articles else 0
        print(f"\n🎯 Performance: Average {avg_time:.2f}s per article")
        
        if avg_time < 10:  # Under 10 seconds per article is good
            print("✅ Performance: EXCELLENT (under 10s per article)")
        elif avg_time < 20:
            print("✅ Performance: GOOD (under 20s per article)")
        else:
            print("⚠️  Performance: SLOW (over 20s per article)")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    print("Groq API Summarizer Performance Test")
    print("====================================")
    
    success = asyncio.run(test_groq_summarizer())
    
    if success:
        print("\n🎉 All tests passed! Groq summarizer is ready.")
        print("💡 The summarizer is now much faster than Ollama!")
    else:
        print("\n💥 Tests failed. Please check the configuration.")
        
    print("\nNext steps:")
    print("1. Add your Groq API key to .env file") 
    print("2. Start the FastAPI server: python -m uvicorn app.main:app --reload")
    print("3. Test the full workflow: curl -X POST http://localhost:8000/news/run")