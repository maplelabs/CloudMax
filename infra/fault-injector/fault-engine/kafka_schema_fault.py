import requests
import time
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def inject_kafka_schema_mismatch_fault(
    fault_service_url: str = "http://localhost:8010",
    fault_name: str = "KAFKA_SCHEMA_MISMATCH_BOOKING_DETAILS",
    duration_minutes: int = 5
):
    """
    Inject Kafka schema mismatch fault for booking details
    
    Args:
        fault_service_url: Base URL of the fault service
        fault_name: Name of the fault flag to manipulate
        duration_minutes: Duration to keep the fault active
    
    Returns:
        Dict with fault injection results
    """
    
    set_url = f"{fault_service_url}/app-fault/{fault_name}/set"
    reset_url = f"{fault_service_url}/app-fault/{fault_name}/reset"
    
    try:
        # Step 1: Set fault flag to TRUE
        logger.info(f"🚀 Setting fault flag: {fault_name}")
        set_response = requests.put(set_url, timeout=30)
        logger.info(f"✅ Fault flag set URL: {set_url}")
        if set_response.status_code == 200:
            logger.info(f"✅ Fault flag set successfully: {fault_name}")
        else:
            logger.error(f"❌ Failed to set fault flag: {set_response.status_code} - {set_response.text}")
            return {"status": "error", "message": f"Failed to set fault: {set_response.text}"}
        
        # Step 2: Sleep for specified duration
        duration_seconds = duration_minutes * 60
        logger.info(f"⏳ Keeping fault active for {duration_minutes} minutes ({duration_seconds} seconds)")
        time.sleep(duration_seconds)
        
        # Step 3: Reset fault flag to FALSE
        logger.info(f"🔄 Resetting fault flag: {fault_name}")
        reset_response = requests.put(reset_url, timeout=30)
        
        if reset_response.status_code == 200:
            logger.info(f"✅ Fault flag reset successfully: {fault_name}")
            return {
                "status": "completed",
                "fault_name": fault_name,
                "duration_minutes": duration_minutes,
                "message": "Kafka schema mismatch fault injection completed successfully"
            }
        else:
            logger.error(f"❌ Failed to reset fault flag: {reset_response.status_code} - {reset_response.text}")
            return {"status": "error", "message": f"Failed to reset fault: {reset_response.text}"}
            
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Network error during fault injection: {e}")
        return {"status": "error", "message": f"Network error: {str(e)}"}
    except Exception as e:
        logger.error(f"❌ Unexpected error during fault injection: {e}")
        return {"status": "error", "message": f"Unexpected error: {str(e)}"}

def reset_kafka_schema_fault(
    fault_service_url: str = "http://fault-service:8080/v1/fault_gen",
    fault_name: str = "KAFKA_SCHEMA_MISMATCH_BOOKING_DETAILS"
):
    """
    Emergency reset of Kafka schema mismatch fault
    
    Args:
        fault_service_url: Base URL of the fault service
        fault_name: Name of the fault flag to reset
    
    Returns:
        Dict with reset results
    """
    
    reset_url = f"{fault_service_url}/app-fault/{fault_name}/reset"
    
    try:
        logger.info(f"🔄 Emergency reset of fault flag: {fault_name}")
        response = requests.put(reset_url, timeout=30)
        
        if response.status_code == 200:
            logger.info(f"✅ Fault flag reset successfully: {fault_name}")
            return {"status": "success", "message": "Fault reset successfully"}
        else:
            logger.error(f"❌ Failed to reset fault flag: {response.status_code} - {response.text}")
            return {"status": "error", "message": f"Failed to reset: {response.text}"}
            
    except Exception as e:
        logger.error(f"❌ Error resetting fault: {e}")
        return {"status": "error", "message": str(e)}

# For direct execution
if __name__ == "__main__":
    result = inject_kafka_schema_mismatch_fault()
    print(f"Fault injection result: {result}")