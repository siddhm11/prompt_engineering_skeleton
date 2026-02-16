
import sys
import os
from unittest.mock import MagicMock, patch

# Add the project root to sys.path to allow imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

# Mock dependencies BEFORE importing the router
sys.modules['backend.core.database'] = MagicMock()
sys.modules['backend.core.security'] = MagicMock()
sys.modules['backend.services.memory_service'] = MagicMock()
sys.modules['backend.services.llm_service'] = MagicMock()

# Mock specific attributes
mock_memory_service = sys.modules['backend.services.memory_service'].MemoryService
mock_memory_service.retrieve_context.return_value = ("Mock Context", 0.5) # Simulating some context
mock_memory_service.get_recent_prompts.return_value = ["Previous Prompt"]

mock_llm_service = sys.modules['backend.services.llm_service']
mock_groq_client = MagicMock()
mock_llm_service.get_groq_client.return_value = mock_groq_client

# Now import the router
from backend.routers.prompts import enhance_prompt, CLASSIFICATION_PROMPT, SIMPLE_SYSTEM_PROMPT, COMPLEX_SYSTEM_PROMPT
from backend.models.schemas import PromptRequest

def test_simple_prompt():
    print("\n--- Testing SIMPLE Prompt ---")
    
    # Setup mock for simple classification
    mock_chat_completion_class = MagicMock()
    mock_chat_completion_class.choices[0].message.content = "SIMPLE"

    # Setup mock for enhancement
    mock_chat_completion_enhance = MagicMock()
    mock_chat_completion_enhance.choices[0].message.content = "Refined Simple Prompt"

    # Configure side_effect to return classification first, then enhancement
    mock_groq_client.chat.completions.create.side_effect = [mock_chat_completion_class, mock_chat_completion_enhance]

    request = PromptRequest(prompt="what is bitcoin", user_id="test_user")
    response = enhance_prompt(request, user_id="test_user")

    print(f"Original: {response['original']}")
    print(f"Enhanced: {response['enhanced']}")
    print(f"Classification: {response.get('classification')}")

    assert response['classification'] == "SIMPLE"
    assert response['enhanced'] == "Refined Simple Prompt"
    print("✅ Simple Test Passed")

def test_complex_prompt():
    print("\n--- Testing COMPLEX Prompt ---")
    
    # Setup mock for complex classification
    mock_chat_completion_class = MagicMock()
    mock_chat_completion_class.choices[0].message.content = "COMPLEX"

    # Setup mock for enhancement
    mock_chat_completion_enhance = MagicMock()
    mock_chat_completion_enhance.choices[0].message.content = "Refined Complex Prompt with Markdown"

    # Configure side_effect to return classification first, then enhancement
    mock_groq_client.chat.completions.create.side_effect = [mock_chat_completion_class, mock_chat_completion_enhance]

    request = PromptRequest(prompt="Write a python script to scrape twitter", user_id="test_user")
    response = enhance_prompt(request, user_id="test_user")

    print(f"Original: {response['original']}")
    print(f"Enhanced: {response['enhanced']}")
    print(f"Classification: {response.get('classification')}")

    assert response['classification'] == "COMPLEX"
    assert response['enhanced'] == "Refined Complex Prompt with Markdown"
    print("✅ Complex Test Passed")

if __name__ == "__main__":

    with open("verify_log.txt", "w", encoding="utf-8") as f:
        try:
            test_simple_prompt()
            test_complex_prompt()
            f.write("🎉 All tests passed!\n")
            print("🎉 All tests passed!")
        except Exception as e:
            f.write(f"❌ Test Failed: {e}\n")
            import traceback
            traceback.print_exc(file=f)
            print(f"❌ Test Failed: {e}")

