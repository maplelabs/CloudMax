import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.server.apis_v1.dependencies import get_db_session
from src.server.models.api.enums import Status
from src.server.models.api.fault_ledger import (
    FaultLedgerCreateRequest, FaultLedgerResponse, FaultLedgerUpdateRequest
)
from src.server.models.db.alert import Alert
from src.server.models.db.evaluation import Evaluation
from src.server.models.db.fault_ledger import FaultLedger, FaultLedgerToAlertMapping
from src.server.utilities.config import is_chaos_system_enabled
from src.triage_evaluation import enqueue_evaluation_job

router = APIRouter(tags=["Fault Ledger"])
logger = logging.getLogger(__name__)


@router.post("", response_model=FaultLedgerResponse, status_code=201)
async def create_fault_ledger(
        payload: FaultLedgerCreateRequest,
        db: AsyncSession = Depends(get_db_session)
):
    """
    Create a new FaultLedger entry with business logic validation.

    Business Logic:
    - Check if ANY fault is in STARTED state (regardless of fault_name):
      - If found: Check if current_time > start_time + configured_duration
      - If yes: Mark the existing started fault as FAILED and accept the new one
      - If no: Reject the new fault (still within duration window)

    Accepts:
    - fault_name: Name of the fault
    - fault_description: Description of the fault
    - start_time: Start time of the fault
    - configured_duration: Duration of the fault in seconds
    - target_system: Target system affected
    - severity: Severity level (low, medium, high, critical)
    - trigger_mechanism: How the fault was triggered
    - session_id: Unique session identifier
    """
    # Check for duplicate session_id
    existing = await db.scalar(
        select(FaultLedger).where(FaultLedger.session_id == payload.session_id)
    )
    if existing:
        logger.warning(f"Duplicate session_id: {payload.session_id}")
        raise HTTPException(
            status_code=400,
            detail=f"Session ID '{payload.session_id}' already exists"
        )

    # Check for ANY started fault (regardless of fault_name)
    # Order by created_at DESC to get the most recent started fault
    started_fault = await db.scalar(
        select(FaultLedger).where(FaultLedger.status == "started").order_by(FaultLedger.created_at.desc())
    )

    if started_fault:
        # Calculate the end time of the started fault
        fault_end_time = started_fault.start_time + timedelta(seconds=started_fault.configured_duration)
        current_time = datetime.now(timezone.utc)

        logger.info(
            f"Found started fault: id={started_fault.id}, fault_name={started_fault.fault_name}, "
            f"start_time={started_fault.start_time}, fault_end_time={fault_end_time}, current_time={current_time}"
        )

        if current_time > fault_end_time:
            # Current time is past the fault duration, mark existing fault as failed
            started_fault.status = "failed"
            logger.info(
                f"Marking started fault {started_fault.id} as FAILED (duration expired). "
                f"Current time {current_time} > fault end time {fault_end_time}"
            )
            await db.commit()
            logger.info(f"Accepted new fault {payload.fault_name} after marking previous one as failed")
        else:
            # Current time is still within the fault duration window
            logger.warning(
                f"Rejecting new fault {payload.fault_name}. "
                f"Started fault {started_fault.id} (fault_name={started_fault.fault_name}) still within duration window. "
                f"Current time {current_time} <= fault end time {fault_end_time}"
            )
            raise HTTPException(
                status_code=409,
                detail=f"Cannot create new fault. "
                       f"A started fault '{started_fault.fault_name}' is still within its duration window. "
                       f"Expires at {fault_end_time.isoformat()}"
            )

    # Create new FaultLedger entry
    # Note: end_time is NOT calculated here - it will be set via PUT endpoint
    new_entry = FaultLedger(
        fault_name=payload.fault_name,
        fault_description=payload.fault_description,
        start_time=payload.start_time,
        end_time=None,  # Will be set via PUT endpoint
        status="started",  # Default status for new entries
        configured_duration=payload.configured_duration,
        target_system=payload.target_system,
        severity=payload.severity,
        trigger_mechanism=payload.trigger_mechanism,
        session_id=payload.session_id,
        alert_names=payload.alert_names
    )

    db.add(new_entry)

    try:
        await db.commit()
        await db.refresh(new_entry)
        logger.info(f"Created FaultLedger entry: id={new_entry.id}, session_id={payload.session_id}")
        return new_entry
    except Exception as e:
        await db.rollback()
        logger.exception(f"Failed to create FaultLedger entry: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create FaultLedger entry")


@router.put("/{session_id}")
async def update_fault_ledger_mapping(
        session_id: str,
        request: FaultLedgerUpdateRequest,
        db: AsyncSession = Depends(get_db_session),
):
    """
    Update a fault ledger entry with end_time and status.
    Also maps alerts to the fault ledger based on time window and alert names.

    Accepts:
    - end_time: Optional end time of the fault
    - status: Optional status (started, failed, completed)
    """
    result = await db.execute(
        select(
            FaultLedger
        ).
        where(
            FaultLedger.session_id == session_id
        )
    )

    fault_ledger = result.scalars().first()

    if not fault_ledger:
        raise HTTPException(status_code=404, detail="Fault ledger entry not found for session_id: " + session_id)

    # Update end_time if provided in request
    if request.end_time is not None:
        fault_ledger.end_time = request.end_time
        logger.info(f"Updated fault_ledger {fault_ledger.id} end_time to {request.end_time}")

    # Update status if provided in request
    if request.status is not None:
        fault_ledger.status = request.status.value
        logger.info(f"Updated fault_ledger {fault_ledger.id} status to {request.status.value}")

    # Filter alerts by time window
    # If end_time is None, use current time as the upper bound
    end_time_for_query = fault_ledger.end_time if fault_ledger.end_time is not None else datetime.now(timezone.utc)

    alert_query = select(
        Alert
    ).where(
        Alert.created_at >= fault_ledger.start_time,
        Alert.created_at <= end_time_for_query
    )

    # Filter by alert_names if available
    if fault_ledger.alert_names is not None and len(fault_ledger.alert_names) > 0:
        alert_query = alert_query.where(
            Alert.alert_name.in_(fault_ledger.alert_names)
        )

    result = await db.execute(alert_query)
    alerts = result.scalars().all()

    logger.info(f"Found {len(alerts)} alerts for fault ledger {fault_ledger.id}")

    # Create mappings for each alert
    mapped_alert_ids = list()

    for alert in alerts:

        # Check if mapping already exists
        existing_mapping = await db.execute(
            select(
                FaultLedgerToAlertMapping
            ).where(
                FaultLedgerToAlertMapping.alert_id == alert.id
            )
        )

        existing_mapping_obj = existing_mapping.scalars().first()

        if existing_mapping_obj:

            logger.info(f"Alert {alert.id} already mapped to fault ledger {existing_mapping_obj.fault_ledger_id}, "
                        f"remapping to fault ledger {fault_ledger.id}")

            mapping = existing_mapping_obj
            mapping.fault_ledger_id = fault_ledger.id

        else:

            # Create new mapping
            mapping = FaultLedgerToAlertMapping(
                fault_ledger_id=fault_ledger.id,
                alert_id=alert.id
            )

            db.add(mapping)

        mapped_alert_ids.append(alert.id)

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception(f"Commit failed while updating fault ledger {fault_ledger.id}, rolled back")
        raise HTTPException(status_code=500, detail="Database commit failed")

    logger.info(f"Created {len(mapped_alert_ids)} alert mappings for fault ledger {fault_ledger.id}")

    # Check if chaos system is enabled
    chaos_enabled = await is_chaos_system_enabled()

    if chaos_enabled:

        logger.info(f"Chaos system enabled, processing {len(mapped_alert_ids)} alerts for evaluation")

        # ✅ CRITICAL FIX: Group alerts by their group_id
        # Alerts may have been grouped AFTER they arrived but BEFORE this PUT request
        alerts_by_group = {}  # {group_id: [alert_ids], None: [standalone_alert_ids]}

        for alert_id in mapped_alert_ids:
            # Fetch alert to check if it has been grouped
            alert = await db.scalar(select(Alert).where(Alert.id == alert_id))

            if not alert:
                logger.warning(f"Alert {alert_id} not found, skipping")
                continue

            if alert.group_id:
                # ✅ Alert belongs to a group (was grouped by batch job)
                if alert.group_id not in alerts_by_group:
                    alerts_by_group[alert.group_id] = []
                alerts_by_group[alert.group_id].append(alert_id)
                logger.info(f"Alert {alert_id} belongs to group {alert.group_id}")
            else:
                # ✅ Standalone alert (never grouped or ungrouped)
                if None not in alerts_by_group:
                    alerts_by_group[None] = []
                alerts_by_group[None].append(alert_id)
                logger.info(f"Alert {alert_id} is standalone (no group)")

        logger.info(f"Grouped alerts for evaluation: {alerts_by_group}")

        # Process each group separately
        for group_id, alert_ids in alerts_by_group.items():
            if group_id is None:
                # ✅ Handle standalone alerts - enqueue individual evaluations
                logger.info(f"Processing {len(alert_ids)} standalone alerts: {alert_ids}")
                for alert_id in alert_ids:
                    eval_record = await db.scalar(
                        select(Evaluation).where(Evaluation.alert_id == alert_id)
                    )

                    if not eval_record:
                        logger.warning(f"Evaluation record not found for alert {alert_id}, skipping (triage may still be in progress)")
                        continue

                    if eval_record.job_id:
                        logger.info(f"Alert {alert_id} already has job_id={eval_record.job_id}, skipping")
                        continue

                    try:
                        job_id = enqueue_evaluation_job(alert_id=alert_id)
                        eval_record.job_id = job_id
                        eval_record.status = Status.QUEUED  # type: ignore
                        logger.info(f"Enqueued individual evaluation for alert {alert_id}, job_id={job_id}")
                    except Exception:
                        logger.exception(f"Failed to enqueue evaluation job for alert {alert_id}")
                        continue

            else:
                # ✅ Handle grouped alerts - enqueue ONE group evaluation
                logger.info(f"Processing group {group_id} with {len(alert_ids)} alerts: {alert_ids}")

                # Look up evaluation record by group_id (NOT alert_id!)
                eval_record = await db.scalar(
                    select(Evaluation).where(Evaluation.group_id == group_id)
                )

                if not eval_record:
                    logger.warning(f"Evaluation record not found for group {group_id}, skipping (triage may still be in progress)")
                    continue

                if eval_record.job_id:
                    logger.info(f"Group {group_id} already has job_id={eval_record.job_id}, skipping")
                    continue

                # Enqueue ONE group evaluation job
                from src.triage_evaluation import enqueue_group_evaluation_job

                try:
                    job_id = enqueue_group_evaluation_job(group_id=group_id)
                    eval_record.job_id = job_id
                    eval_record.status = Status.QUEUED  # type: ignore
                    logger.info(f"✅ Enqueued group evaluation for group_id={group_id}, "
                               f"job_id={job_id}, covering {len(alert_ids)} alerts: {alert_ids}")
                except Exception:
                    logger.exception(f"Failed to enqueue group evaluation job for group {group_id}")
                    continue

        # Commit all job_id updates
        try:
            await db.commit()
            logger.info("Evaluation job enqueueing complete")
        except Exception:
            await db.rollback()
            logger.exception(f"Commit failed while saving job IDs for fault ledger {fault_ledger.id}, rolled back")
            raise HTTPException(status_code=500, detail="Database commit failed")

    else:

        logger.info("Chaos system disabled, skipping evaluation job enqueueing")
