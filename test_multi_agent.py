#!/usr/bin/env python3
"""
Test script for the multi-agent news processing system.

This script tests:
1. Groq AutoGen client integration
2. Individual agent creation and configuration
3. Multi-agent conversation flow
4. End-to-end article processing

Usage:
    python test_multi_agent.py
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add the app directory to Python path
sys.path.append('/Users/muhammadusman/Projects/Learning/python/ai-news-summarizer')

from app.agents.simple_multi_agent import SimpleMultiAgentProcessor as MultiAgentNewsProcessor
from app.services.groq_client import GroqClient
from app.config.logging import setup_logging, get_logger

# Setup logging
setup_logging()
logger = get_logger(__name__)


async def test_groq_client():
    """Test the Groq client integration."""
    print("\n🧪 Testing Groq Client...")
    
    try:
        client = GroqClient()
        
        # Test client creation
        response = await client.chat(
            messages=[
                {"role": "system", "content": "You are a helpful AI assistant."},
                {"role": "user", "content": "Hello, can you respond with 'Multi-agent integration working!'?"}
            ],
            model="llama-3.1-8b-instant"
        )
        
        print(f"✅ Groq client response: {response}")
        return True
        
    except Exception as e:
        print(f"❌ Groq client test failed: {e}")
        return False


async def test_single_article_processing():
    """Test processing a single article through the multi-agent system."""
    print("\n🤖 Testing Single Article Multi-Agent Processing...")
    
    # Sample article for testing
    test_article = {
        "title": "OpenAI Launches GPT-4 Turbo with Enhanced Capabilities",
        "content": """
        OpenAI has announced the release of GPT-4 Turbo, featuring significant improvements in reasoning, 
        code generation, and multimodal capabilities. The new model can process up to 128,000 tokens in context, 
        allowing for more comprehensive analysis and longer conversations. Key enhancements include better 
        mathematical reasoning, improved coding abilities, and more accurate instruction following.
        
        The model also introduces function calling capabilities that allow developers to integrate GPT-4 Turbo 
        with external APIs and tools. This enables the creation of more sophisticated applications that can 
        perform real-world tasks beyond text generation.
        
        OpenAI reports that GPT-4 Turbo is significantly more cost-effective than its predecessor, with pricing 
        reduced by up to 3x for input tokens. The model is now available through the OpenAI API for developers 
        and organizations worldwide.
        """,
        "url": "https://example.com/openai-gpt4-turbo",
        "published": "2024-01-15T10:00:00Z"
    }
    
    try:
        # Create multi-agent processor
        processor = MultiAgentNewsProcessor("test_job_001")
        
        # Process the test article
        print("📋 Processing article with multi-agent collaboration...")
        result = await processor.process_articles([test_article])
        
        print("✅ Multi-agent processing completed!")
        print(f"📊 Success rate: {result['success_count']}/{result['total_count']}")
        
        if result['results']:
            article_result = result['results'][0]
            print(f"\n📰 Article: {article_result['article_title'][:50]}...")
            print(f"📝 Summary: {article_result['summary'][:100]}...")
            print(f"🎯 Key Points: {len(article_result['key_points'])} points")
            print(f"🔍 Analysis: {article_result['analysis'][:100]}...")
            
            # Show agent conversation highlights
            if article_result.get('agent_conversation'):
                print(f"💬 Agent Messages: {len(article_result['agent_conversation'])} exchanges")
        
        return True
        
    except Exception as e:
        print(f"❌ Single article processing failed: {e}")
        logger.error("Test failed", error=str(e), exc_info=True)
        return False


async def test_multiple_articles_processing():
    """Test processing multiple articles with concurrency."""
    print("\n📚 Testing Multiple Articles Multi-Agent Processing...")
    
    # Multiple test articles
    test_articles = [
        {
            "title": "Microsoft Integrates AI into Office Suite",
            "content": "Microsoft announced comprehensive AI integration across Office 365 applications, including Word, Excel, and PowerPoint. The new features include intelligent content generation, automated data analysis, and enhanced collaboration tools.",
            "url": "https://example.com/microsoft-ai-office"
        },
        {
            "title": "Google Unveils Quantum Computing Breakthrough", 
            "content": "Google researchers have achieved a major breakthrough in quantum error correction, bringing practical quantum computing significantly closer to reality. The new system demonstrates unprecedented stability and error rates.",
            "url": "https://example.com/google-quantum-breakthrough"
        },
        {
            "title": "Tesla Announces Full Self-Driving Beta Expansion",
            "content": "Tesla is expanding its Full Self-Driving beta program to 100,000 additional users across North America. The latest version includes improved city driving capabilities and enhanced safety features.",
            "url": "https://example.com/tesla-fsd-expansion"
        }
    ]
    
    try:
        # Create multi-agent processor
        processor = MultiAgentNewsProcessor("test_job_multi_002")
        
        # Process multiple articles
        print(f"🔄 Processing {len(test_articles)} articles with parallel multi-agent collaboration...")
        result = await processor.process_articles(test_articles)
        
        print("✅ Multi-article processing completed!")
        print(f"📊 Success rate: {result['success_count']}/{result['total_count']}")
        
        # Display results summary
        for i, article_result in enumerate(result['results'], 1):
            print(f"\n📄 Article {i}: {article_result['article_title'][:40]}...")
            print(f"   📋 Summary length: {len(article_result['summary'])} chars")
            print(f"   🎯 Key points: {len(article_result['key_points'])}")
            print(f"   🔍 Implications: {len(article_result['implications'])}")
        
        return True
        
    except Exception as e:
        print(f"❌ Multiple articles processing failed: {e}")
        logger.error("Multi-article test failed", error=str(e), exc_info=True)
        return False


async def test_agent_output_parsing():
    """Test parsing of structured agent output."""
    print("\n🔧 Testing Agent Output Parsing...")
    
    # Sample agent output to parse
    sample_output = """
=== FINAL NEWS SUMMARY ===
HEADLINE: AI Breakthrough Revolutionizes Industry
SUMMARY: A major advancement in artificial intelligence has been announced by researchers, promising to transform multiple industries. The breakthrough focuses on improved reasoning capabilities and enhanced efficiency.

KEY POINTS:
• Revolutionary AI architecture developed
• 50% improvement in reasoning accuracy
• Applications across healthcare and finance
• Commercial availability expected in 2024

=== ANALYSIS ===
SIGNIFICANCE: This represents a fundamental shift in AI capabilities
STRATEGIC IMPLICATIONS:
• Business processes will be automated at unprecedented scale
• Technology companies will need to adapt quickly
• Market disruption expected across multiple sectors
OUTLOOK: Widespread adoption likely within 18 months
    """
    
    try:
        processor = MultiAgentNewsProcessor("test_parsing")
        
        # Test parsing
        parsed = processor._parse_coordinator_output(sample_output)
        
        print("✅ Output parsing successful!")
        print(f"📝 Summary: {parsed['summary'][:60]}...")
        print(f"🎯 Key points: {len(parsed['key_points'])}")
        print(f"🔍 Analysis: {parsed['analysis'][:60]}...")
        print(f"📈 Implications: {len(parsed['implications'])}")
        
        return True
        
    except Exception as e:
        print(f"❌ Output parsing test failed: {e}")
        return False


async def main():
    """Run all multi-agent system tests."""
    print("🚀 Starting Multi-Agent News Processing System Tests")
    print("=" * 60)
    
    # Check environment
    if not os.getenv("GROQ_API_KEY"):
        print("❌ GROQ_API_KEY environment variable not set!")
        print("Please set your Groq API key: export GROQ_API_KEY='your_key_here'")
        return
    
    test_results = []
    
    # Run tests
    tests = [
        ("Groq Client", test_groq_client),
        ("Agent Output Parsing", test_agent_output_parsing),
        ("Single Article Processing", test_single_article_processing),
        ("Multiple Articles Processing", test_multiple_articles_processing),
    ]
    
    for test_name, test_func in tests:
        print(f"\n🔄 Running: {test_name}")
        try:
            result = await test_func()
            test_results.append((test_name, result))
            if result:
                print(f"✅ {test_name}: PASSED")
            else:
                print(f"❌ {test_name}: FAILED")
        except Exception as e:
            print(f"💥 {test_name}: ERROR - {e}")
            test_results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in test_results if result)
    total = len(test_results)
    
    for test_name, result in test_results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")
    
    print(f"\n🏆 Overall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Multi-agent system is ready.")
    else:
        print("⚠️ Some tests failed. Check configuration and dependencies.")


if __name__ == "__main__":
    asyncio.run(main())