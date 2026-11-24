"""
Chaos Toolkit Actions for Elasticsearch Bucket Management
"""
import requests
from typing import Dict, Any, Optional
from datetime import datetime


def update_bucket_size(bucket_size: int = 4, elasticsearch_url: str = "http://localhost:9200") -> bool:
    """
    Update the Elasticsearch max_buckets cluster setting and verify the update.
    Args:
        bucket_size: The maximum number of buckets to allow (default: 4)
        elasticsearch_url: The Elasticsearch base URL (default: http://localhost:9200)
    Returns:
        bool: True if the bucket size was successfully updated and verified, False otherwise
    Example response from Elasticsearch:
        {
            "acknowledged": true,
            "persistent": {
                "search": {
                    "max_buckets": "4"
                }
            },
            "transient": {}
        }
    """

    url = f"{elasticsearch_url}/_cluster/settings"

    headers = {
        "Content-Type": "application/json"
    }

    body = {
        "persistent": {
            "search.max_buckets": bucket_size
        }
    }

    try:
        response = requests.put(url, json=body, headers=headers)
        response.raise_for_status()

        result = response.json()

        print(f"Successfully sent update request for max_buckets to {bucket_size}")
        print(f"Response: {result}")

        # Verify the update by calling get_bucket_size
        actual_bucket_size = get_bucket_size(elasticsearch_url=elasticsearch_url)

        # Check if the actual bucket size matches the requested bucket size
        if actual_bucket_size == bucket_size:
            print(f"Verification successful: Bucket size is {actual_bucket_size}")
            return True
        else:
            error_msg = f"Verification failed: Expected bucket size {bucket_size}, but got {actual_bucket_size}"
            print(error_msg)
            return False

    except requests.exceptions.RequestException as e:
        error_msg = f"Failed to update bucket size: {str(e)}"
        print(error_msg)
        return False
    except Exception as e:
        error_msg = f"Error during verification: {str(e)}"
        print(error_msg)
        return False


def get_filter(
    token: str,
    location: str = "Mumbai",
    checkin_date: str = "2025-12-06",
    checkout_date: str = "2025-12-08",
    guests: int = 0,
    price_min: str = "",
    price_max: str = "",
    rating_min: str = "",
    bff_url: str = "http://localhost:3000"
) -> bool:
    """
    Get hotel filters from the BFF API.
    Args:
        token: JWT Bearer token for authentication
        location: Location to search (default: Mumbai)
        checkin_date: Check-in date in YYYY-MM-DD format (default: 2025-12-06)
        checkout_date: Check-out date in YYYY-MM-DD format (default: 2025-12-08)
        guests: Number of guests (default: 0)
        price_min: Minimum price filter (default: empty string)
        price_max: Maximum price filter (default: empty string)
        rating_min: Minimum rating filter (default: empty string)
        bff_url: BFF service base URL (default: http://localhost:3000)
    Returns:
        bool: True if no error found, False if error found
    Example success response:
        {
            "success": true,
            "message": "Filters retrieved successfully",
            "data": {
                "price_range": {"min": 6500, "max": 8000},
                "rating_range": {"min": 4.3, "max": 4.5},
                "room_types": ["deluxe", "suite", "presidential", "standard"],
                "amenities": {"breakfast": 1, "parking": 2, "wifi": 2, "pool": 2, "gym": 2},
                "policies": {"free_cancellation": 2, "no_prepayment": 1, "pets_allowed": 1}
            },
            "error": null,
            "timestamp": "2025-12-04T05:42:53.277Z"
        }
        Returns: True
    Example error response (when bucket limit exceeded):
        {
            "success": false,
            "message": "Filters retrieval failed!",
            "data": {},
            "error": "Trying to create too many buckets. Must be less than or equal to: [3] but this number of buckets was exceeded. This limit can be set by changing the [search.max_buckets] cluster level setting.",
            "timestamp": "2025-12-05T10:02:22.207Z"
        }
        Returns: False
    """
    url = f"{bff_url}/api/hotels/filters"

    # Build query parameters
    params = {
        "location": location,
        "checkin_date": checkin_date,
        "checkout_date": checkout_date,
        "guests": guests,
        "price_min": price_min,
        "price_max": price_max,
        "rating_min": rating_min
    }

    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()

        result = response.json()

        # Check if the response contains an error in the data field
        if result.get("success") and "data" in result:
            data = result["data"]

            # Check if data contains an error (bucket limit exceeded)
            if isinstance(data, dict) and "error" in data:
                error_msg = data["error"]
                print(f"Filter API returned error: {error_msg}")

                # Check if it's a bucket limit error
                if "search_phase_execution_exception" in error_msg or "too_many_buckets" in error_msg:
                    print(f"BUCKET LIMIT EXCEEDED!")
                    print(f"   This indicates max_buckets is set too low")
                    print(f"   The application needs at least 4 buckets for room types")

                # Error found - return False
                return False
            else:
                # Success - display summary
                print(f"Filters retrieved successfully")

                if "room_types" in data:
                    room_types = data["room_types"]
                    print(f"   Room types found: {len(room_types)} - {room_types}")

                if "price_range" in data:
                    price_range = data["price_range"]
                    print(f"   Price range: ${price_range.get('min', 0)} - ${price_range.get('max', 0)}")

                if "rating_range" in data:
                    rating_range = data["rating_range"]
                    print(f"   Rating range: {rating_range.get('min', 0)} - {rating_range.get('max', 0)}")

                # No error found - return True
                return True

        # If response structure is unexpected, consider it an error
        print(f"Unexpected response structure")
        return False

    except requests.exceptions.RequestException as e:
        error_msg = f"Failed to get filters: {str(e)}"
        print(error_msg)

        # Try to get response body if available
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_body = e.response.json()
                print(f"   Response body: {error_body}")
            except:
                print(f"   Response text: {e.response.text}")

        # Request failed - return False
        return False

def get_bucket_size(elasticsearch_url: str = "http://localhost:9200") -> int:
    """
    Get the current Elasticsearch max_buckets cluster setting.
    
    Args:
        elasticsearch_url: The Elasticsearch base URL (default: http://localhost:9200)
    
    Returns:
        int: The current max_buckets value
        
    Example response structure:
        {
            "persistent": {
                "indices": {
                    "breaker": {
                        "total": {
                            "limit": "19%"
                        }
                    }
                },
                "search": {
                    "max_buckets": "4"
                }
            },
            "transient": {}
        }
    """
    url = f"{elasticsearch_url}/_cluster/settings?include_defaults=true"

    try:
        response = requests.get(url)
        response.raise_for_status()

        result = response.json()

        # Extract max_buckets from persistent.search.max_buckets
        max_buckets = None

        # Try to get from persistent settings first
        if "persistent" in result and "search" in result["persistent"]:
            max_buckets_value = result["persistent"]["search"].get("max_buckets")
            if max_buckets_value:
                max_buckets = int(max_buckets_value)

        # If not in persistent, try transient settings
        if max_buckets is None and "transient" in result and "search" in result["transient"]:
            max_buckets_value = result["transient"]["search"].get("max_buckets")
            if max_buckets_value:
                max_buckets = int(max_buckets_value)

        # If not in persistent or transient, try defaults
        if max_buckets is None and "defaults" in result and "search" in result["defaults"]:
            max_buckets_value = result["defaults"]["search"].get("max_buckets")
            if max_buckets_value:
                max_buckets = int(max_buckets_value)

        if max_buckets is not None:
            print(f"Current max_buckets: {max_buckets}")
            return max_buckets
        else:
            print("max_buckets setting not found, using default (10000)")
            return 10000  # Elasticsearch default

    except requests.exceptions.RequestException as e:
        error_msg = f"Failed to get bucket size: {str(e)}"
        print(error_msg)
        raise Exception(error_msg)


def get_bucket_size_detailed(elasticsearch_url: str = "http://localhost:9200") -> Dict[str, Any]:
    """
    Get the detailed Elasticsearch cluster settings including max_buckets.
    
    Args:
        elasticsearch_url: The Elasticsearch base URL (default: http://localhost:9200)
    
    Returns:
        Dict containing the full cluster settings response
    """
    url = f"{elasticsearch_url}/_cluster/settings?include_defaults=true"

    try:
        response = requests.get(url)
        response.raise_for_status()

        result = response.json()

        print(f"Retrieved cluster settings")

        # Extract and display max_buckets if available
        if "persistent" in result and "search" in result["persistent"]:
            max_buckets = result["persistent"]["search"].get("max_buckets")
            if max_buckets:
                print(f"   max_buckets (persistent): {max_buckets}")

        return result

    except requests.exceptions.RequestException as e:
        error_msg = f"Failed to get cluster settings: {str(e)}"
        print(error_msg)
        raise Exception(error_msg)