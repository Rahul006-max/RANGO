

def test_model_connectivity(
    provider: str,
    api_url: str,
    api_key: str,
) -> Dict[str, Any]:
    """
    Test connectivity to a model API endpoint without requiring a model_name.
    Supports Ollama, OpenAI, Anthropic, and custom OpenAI-compatible endpoints.
    """
    provider = provider.lower()
    
    try:
        import requests
        
        if provider == "ollama":
            response = requests.get(
                f"{api_url.rstrip('/')}/api/tags",
                timeout=5
            )
            if response.status_code == 200:
                return {"status": "connected", "message": "Ollama connection successful"}
            return {
                "error": f"Ollama connection failed: {response.status_code}",
                "status_code": 400,
            }
        
        elif provider == "openai":
            headers = {"Authorization": f"Bearer {api_key}"}
            response = requests.get(
                "https://api.openai.com/v1/models",
                headers=headers,
                timeout=5
            )
            if response.status_code == 200:
                return {"status": "connected", "message": "OpenAI connection successful"}
            return {
                "error": f"OpenAI authentication failed: {response.status_code}",
                "status_code": 401,
            }
        
        elif provider == "anthropic":
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01"
            }
            response = requests.get(
                "https://api.anthropic.com/v1/models",
                headers=headers,
                timeout=5
            )
            if response.status_code == 200:
                return {"status": "connected", "message": "Anthropic connection successful"}
            return {
                "error": f"Anthropic authentication failed: {response.status_code}",
                "status_code": 401,
            }
        
        elif provider == "custom":
            headers = {"Authorization": f"Bearer {api_key}"}
            response = requests.get(
                f"{api_url.rstrip('/')}/models",
                headers=headers,
                timeout=5
            )
            if response.status_code == 200:
                return {"status": "connected", "message": "Custom API connection successful"}
            return {
                "error": f"Custom API connection failed: {response.status_code}",
                "status_code": 400,
            }
        
        return {
            "error": f"Provider '{provider}' not supported for testing",
            "status_code": 400,
        }
    
    except requests.exceptions.Timeout:
        return {
            "error": "Connection timeout. Check the API URL and network connectivity.",
            "status_code": 408,
        }
    except requests.exceptions.ConnectionError:
        return {
            "error": "Could not connect to API endpoint. Check the URL.",
            "status_code": 400,
        }
    except Exception as e:
        return {
            "error": f"Connection test failed: {str(e)}",
            "status_code": 400,
        }
