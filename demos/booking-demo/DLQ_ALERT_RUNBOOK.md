# Dead Letter Queue Alert - Advanced Diagnostic Runbook

## Alert Overview

**Alert Condition:** `kafka_topic_partition_current_offset{topic="booking-events-dlq"} > 0`  
**Threshold:** Greater than 0  
**Severity:** Critical  
**Impact:** Messages failing to process, leading to incomplete business transactions

---

## Diagnostic Workflow

### Step 1: Identify Affected Entities in Alert Time Window

**Objective:** Discover all entities (bookings, orders, transactions) created during the alert period

**Method:** Query the primary database table for entities created within ±10 minutes of alert creation time

**Inputs:**
- Alert creation timestamp
- Time window (default: 10 minutes before/after alert)
- Primary table name (e.g., `booking_info`, `orders`, `transactions`)

**Expected Output:**
- List of entity IDs (e.g., `[6, 7, 8, 9]`)
- Count of entities found
- Time range searched

**Success Criteria:**
- Query returns successfully
- At least one entity found in time window

**If No Entities Found:**
- ⚠️ Possible false positive alert
- 🔍 Check if DLQ contains messages older than the time window
- 🔍 Verify alert timestamp is correct

---

### Step 2: Determine Processing Status for Each Entity

**Objective:** Identify which entities failed processing and at what stage

**Method:** For each entity ID from Step 1, check:
1. Presence in primary database table (entity created)
2. Presence in secondary/processed table (processing completed)
3. Message existence in source Kafka topic
4. Consumer offset position relative to message offset

**Processing Status Categories:**

| Status | Database Primary | Database Secondary | Kafka Message | Consumer Offset | Interpretation |
|--------|-----------------|-------------------|---------------|-----------------|----------------|
| **PROCESSED** | ✅ Yes | ✅ Yes | ✅ Found | Committed past message | Successfully completed |
| **PENDING** | ✅ Yes | ❌ No | ✅ Found | Not reached message yet | Consumer lag - waiting to process |
| **CONSUMED_BUT_NOT_PROCESSED** | ✅ Yes | ❌ No | ✅ Found | Committed past message | Consumer read but failed to process |
| **PRODUCER_EXCEPTION** | ✅ Yes | ❌ No | ❌ Not found | N/A | Entity created but never published |
| **NOT_FOUND** | ❌ No | ❌ No | ❌ Not found | N/A | Entity doesn't exist |

**Categorize Results:**
```
✅ Successfully Processed: [7, 9]
⏳ Pending (Consumer Lag): [8]
⚠️ Consumed But Not Processed: [6]
❌ Producer Exception: []
```

**Next Actions Based on Status:**
- If any **PENDING** → Proceed to Step 3 (Check Consumer Lag)
- If any **CONSUMED_BUT_NOT_PROCESSED** → Proceed to Step 4 (Check DLQ)
- If any **PRODUCER_EXCEPTION** → Check producer service logs
- If all **PROCESSED** → False positive, verify alert configuration

---

### Step 3: Analyze Consumer Lag (If Entities Are Pending)

**Objective:** Determine if consumer is falling behind message production rate

**Method:** Query consumer group metadata for:
- Current offset (latest message in topic)
- Committed offset (last message consumer processed)
- Lag per partition
- Total lag across all partitions

**Lag Severity Matrix:**

| Total Lag | Status | Severity | Action Required |
|-----------|--------|----------|-----------------|
| 0-10 | ✅ Healthy | None | No action needed |
| 11-100 | ⚠️ Minor lag | Low | Monitor trend |
| 101-500 | 🔴 Lagging | Medium | Scale up consumers |
| 501-1000 | 🔴 Severe lag | High | Immediate scaling required |
| > 1000 | 🚨 Critical lag | Critical | Emergency scaling + investigation |

**Decision Logic:**
- **If lag > 100:** Root cause is consumer capacity → Skip to Step 6 (Remediation)
- **If lag ≤ 100:** Consumer is healthy, failures are message-specific → Continue to Step 4

---

### Step 4: Search DLQ for Failed Entities

**Objective:** Find error details for entities that were consumed but not processed

**Method:** For each entity with status **CONSUMED_BUT_NOT_PROCESSED**:
1. Search DLQ topic for messages containing the entity ID
2. Use time window optimization (±10 minutes from alert time)
3. Extract error message and failure reason

**Search Parameters:**
- Entity ID to search for
- DLQ topic name (typically `{source-topic}-dlq`)
- Alert creation timestamp
- Time window (default: 10 minutes)

**Expected Output Per Entity:**

| Status | Meaning | Next Action |
|--------|---------|-------------|
| **FOUND** | Entity message exists in DLQ with error details | Analyze error message → Step 5 |
| **NOT_FOUND** | Entity consumed but not in DLQ or processed table | Check consumer logs for silent failures |

**Collect Error Patterns:**
```
Entity 6:  "Schema validation failed: missing required field 'email'"
Entity 10: "Schema validation failed: missing required field 'email'"
Entity 12: "Database connection timeout after 30s"
Entity 15: "Null pointer exception in field 'address.zipcode'"
```

---

### Step 5: Root Cause Analysis

**Objective:** Determine the underlying cause based on diagnostic data

#### Decision Tree:

```
┌─ No entities found in time window
│  └─ ROOT CAUSE: False positive or stale alert
│     ACTION: Verify alert configuration and DLQ message timestamps
│
├─ All entities status = PROCESSED
│  └─ ROOT CAUSE: False positive - all entities processed successfully
│     ACTION: Check if DLQ metric is stale or alert threshold too sensitive
│
├─ Any entity status = PRODUCER_EXCEPTION
│  └─ ROOT CAUSE: Message broker producer failure
│     ACTION: Check producer service logs and broker connectivity
│
├─ Any entity status = PENDING + Consumer lag > 100
│  └─ ROOT CAUSE: Consumer capacity insufficient
│     ACTION: Scale consumer instances
│     SEVERITY: Based on lag severity matrix
│
└─ Any entity status = CONSUMED_BUT_NOT_PROCESSED + Found in DLQ
   │
   ├─ Error contains: "schema", "validation", "deserialize"
   │  └─ ROOT CAUSE: Schema mismatch or validation failure
   │     ACTION: Fix message schema or update consumer schema version
   │     PATTERN: Check if multiple entities have same error
   │
   ├─ Error contains: "database", "connection", "timeout", "pool"
   │  └─ ROOT CAUSE: Database connectivity or performance issue
   │     ACTION: Check database connection pool, network, and query performance
   │     PATTERN: May affect all entities in time window
   │
   ├─ Error contains: "null", "required field", "missing"
   │  └─ ROOT CAUSE: Invalid or incomplete message data
   │     ACTION: Fix data validation in producer service
   │     PATTERN: Identify which fields are commonly missing
   │
   ├─ Error contains: "permission", "access denied", "unauthorized"
   │  └─ ROOT CAUSE: Authorization or authentication failure
   │     ACTION: Check service credentials and permissions
   │
   └─ Other error patterns
      └─ ROOT CAUSE: Business logic or application error
         ACTION: Investigate consumer application code
         PATTERN: Group by error message to find common issues
```

#### Root Cause Output Format:

```json
{
  "root_cause": "Schema validation failure",
  "category": "DATA_QUALITY",
  "severity": "HIGH",
  "affected_entities": [6, 10],
  "total_entities_in_window": 4,
  "success_rate": "50%",
  "error_pattern": "missing required field 'email'",
  "first_occurrence": "2025-12-12T14:05:30Z",
  "last_occurrence": "2025-12-12T14:18:45Z",
  "recommended_action": "Update producer to include 'email' field or make it optional in consumer schema"
}
```

---

### Step 6: Remediation Actions

**Objective:** Execute corrective actions based on identified root cause

#### Remediation Matrix:

| Root Cause Category | Immediate Action | Follow-up Action | Priority |
|---------------------|------------------|------------------|----------|
| **Consumer Capacity (Lag)** | Scale consumer instances horizontally | Implement auto-scaling based on lag metrics | 🔴 Critical |
| **Schema Mismatch** | Identify schema version conflict | Update consumer schema or fix producer schema | 🔴 Critical |
| **Database Connectivity** | Check connection pool exhaustion | Increase pool size or optimize queries | 🔴 Critical |
| **Invalid Data** | Identify missing/invalid fields | Add validation in producer before publishing | 🟡 High |
| **Producer Failure** | Check message broker connectivity | Verify network, credentials, and broker health | 🔴 Critical |
| **Authorization** | Verify service credentials | Update credentials or permissions | 🟡 High |
| **Business Logic Error** | Review consumer code for bugs | Fix application logic and deploy | 🟡 High |
| **False Positive** | Adjust alert threshold or time window | Update monitoring configuration | 🟢 Low |

#### Remediation Steps by Root Cause:

**For Consumer Capacity Issues (Lag > 100):**
1. Scale consumer deployment to increase parallelism
2. Verify scaling by checking active consumer instances
3. Monitor lag reduction over 5-10 minutes
4. If lag persists, investigate consumer performance (CPU, memory, processing time)
5. Consider partitioning strategy optimization

**For Schema Validation Failures:**
1. Extract sample DLQ message for analysis
2. Compare message schema with consumer expected schema
3. Identify missing, extra, or mismatched fields
4. Determine if producer or consumer schema needs update
5. Create ticket for schema evolution with backward compatibility
6. Test schema change in staging environment
7. Deploy schema fix to production

**For Database Connectivity Issues:**
1. Check current database connection pool settings
2. Query active connections vs. maximum allowed
3. Identify long-running queries blocking connections
4. Check network connectivity between consumer and database
5. Review database performance metrics (CPU, memory, disk I/O)
6. Increase connection pool size if exhausted
7. Optimize slow queries if identified

**For Invalid Message Data:**
1. Extract DLQ messages to identify data quality issues
2. Identify common patterns (missing fields, null values, format errors)
3. Trace back to producer service generating invalid data
4. Add validation logic in producer before message publication
5. Implement schema validation at producer side
6. Add monitoring for data quality metrics

**For Producer Failures:**
1. Check producer service logs for errors
2. Verify message broker connectivity and health
3. Check network policies and firewall rules
4. Verify authentication credentials
5. Check broker capacity and quotas
6. Review producer configuration (timeouts, retries, batching)

**For Silent Consumer Failures (Consumed but not in DLQ):**
1. Enable debug/trace logging in consumer
2. Check for unhandled exceptions in consumer code
3. Verify DLQ error handling is implemented correctly
4. Check if consumer is swallowing exceptions
5. Add comprehensive error handling and DLQ publishing

---

### Step 7: Verification & Monitoring

**Objective:** Confirm issue resolution and prevent recurrence

#### Verification Checklist:

**Immediate Verification (0-5 minutes):**
- [ ] DLQ offset returns to 0 or stops increasing
- [ ] Consumer lag decreases to healthy levels (< 10)
- [ ] No new error messages appearing in DLQ
- [ ] Alert auto-resolves or stops firing

**Short-term Verification (5-30 minutes):**
- [ ] Create test entity and verify end-to-end processing
- [ ] Confirm test entity appears in both primary and secondary tables
- [ ] Monitor consumer lag remains stable
- [ ] Check consumer error logs for new failures

**Long-term Monitoring (1-24 hours):**
- [ ] Monitor DLQ offset trend over time
- [ ] Track consumer lag patterns
- [ ] Review error rate metrics
- [ ] Verify no regression in processing throughput

#### Monitoring Queries:

**Check DLQ Offset Trend:**
```
Query: kafka_topic_partition_current_offset{topic="*-dlq"}
Expected: Should be 0 or not increasing
Alert if: Increases by > 10 in 5 minutes
```

**Check Consumer Lag:**
```
Query: kafka_consumer_group_lag{group="*-processing-group"}
Expected: < 10 messages
Alert if: > 100 messages for > 5 minutes
```

**Check Processing Success Rate:**
```
Query: (entities_processed_total / entities_created_total) * 100
Expected: > 95%
Alert if: < 90% for > 10 minutes
```

**Check Consumer Error Rate:**
```
Query: rate(consumer_errors_total[5m])
Expected: < 0.1 errors/second
Alert if: > 1 error/second for > 5 minutes
```

---

### Step 8: Post-Incident Actions

**Objective:** Learn from incident and improve system resilience

#### Immediate Post-Incident (Within 24 hours):

1. **Document Incident:**
   - Root cause identified
   - Affected entities and time range
   - Resolution steps taken
   - Time to detection (TTD)
   - Time to resolution (TTR)

2. **Update Runbook:**
   - Add new error patterns discovered
   - Document effective remediation steps
   - Update decision tree with new scenarios

3. **Share Learnings:**
   - Brief team on incident and resolution
   - Update on-call documentation
   - Share in incident review channel

#### Short-term Improvements (Within 1 week):

1. **Enhance Monitoring:**
   - Add alerts for newly discovered failure modes
   - Improve alert signal-to-noise ratio
   - Add dashboards for key metrics

2. **Improve Error Handling:**
   - Add better error messages to DLQ
   - Include context (timestamps, entity IDs, stack traces)
   - Implement structured logging

3. **Add Preventive Measures:**
   - Implement validation before message publishing
   - Add circuit breakers for external dependencies
   - Implement retry logic with exponential backoff

#### Long-term Improvements (Within 1 month):

| Improvement | Description | Impact | Effort |
|-------------|-------------|--------|--------|
| **Schema Registry** | Centralized schema management with versioning | Prevents schema mismatch errors | Medium |
| **Auto-scaling** | Scale consumers based on lag metrics | Prevents capacity issues | Medium |
| **DLQ Replay Tool** | Automated replay of fixed messages | Faster recovery from failures | High |
| **Data Validation Framework** | Centralized validation before publishing | Prevents invalid data errors | High |
| **Chaos Engineering** | Regular failure injection testing | Improves resilience | Medium |
| **Observability Enhancement** | Distributed tracing, better metrics | Faster diagnosis | Medium |
| **Consumer Performance Optimization** | Profile and optimize slow consumers | Reduces lag | High |
| **Database Connection Pooling** | Optimize connection management | Prevents connection exhaustion | Low |

---

## Appendix A: Common Error Patterns

### Schema and Validation Errors

| Error Pattern | Root Cause | Solution |
|---------------|------------|----------|
| `missing required field 'X'` | Producer not sending field or consumer expecting new field | Add field to producer or make optional in consumer |
| `unknown field 'Y'` | Producer sending extra field consumer doesn't recognize | Update consumer schema or configure to ignore unknown fields |
| `type mismatch: expected string, got integer` | Schema evolution without backward compatibility | Use schema registry with compatibility rules |
| `deserialization failed` | Message format incompatible with consumer | Verify serialization format (JSON, Avro, Protobuf) matches |

### Database Errors

| Error Pattern | Root Cause | Solution |
|---------------|------------|----------|
| `connection timeout` | Connection pool exhausted or network issue | Increase pool size, check network, optimize queries |
| `deadlock detected` | Concurrent transactions conflicting | Review transaction isolation levels, add retry logic |
| `duplicate key violation` | Attempting to insert existing record | Add idempotency checks, use upsert instead of insert |
| `foreign key constraint violation` | Referenced entity doesn't exist | Ensure proper ordering of entity creation |

### Application Errors

| Error Pattern | Root Cause | Solution |
|---------------|------------|----------|
| `null pointer exception` | Missing null checks in code | Add defensive null checks, use optional types |
| `index out of bounds` | Array/list access without bounds checking | Validate collection sizes before access |
| `division by zero` | Missing validation for zero values | Add validation before arithmetic operations |
| `timeout waiting for response` | External service slow or unavailable | Add circuit breaker, implement timeouts |

---

## Appendix B: Diagnostic Data Collection Template

Use this template to collect diagnostic data during incident investigation:

```markdown
## Incident Diagnostic Data

**Alert Details:**
- Alert Name:
- Alert Timestamp:
- Severity:
- Alert Value:

**Step 1: Entity Discovery**
- Time Window: [start] to [end]
- Entities Found: []
- Total Count:

**Step 2: Processing Status**
- Successfully Processed: []
- Pending (Lag): []
- Consumed But Not Processed: []
- Producer Exception: []
- Not Found: []

**Step 3: Consumer Lag Analysis**
- Consumer Group:
- Total Lag:
- Lag Status:
- Per-Partition Lag:

**Step 4: DLQ Search Results**
- Entities in DLQ: []
- Common Error Pattern:
- Sample Error Message:

**Step 5: Root Cause**
- Root Cause:
- Category:
- Severity:
- Affected Count:
- Success Rate:

**Step 6: Remediation**
- Actions Taken:
- Timestamp:
- Result:

**Step 7: Verification**
- DLQ Offset After Fix:
- Consumer Lag After Fix:
- Test Entity Processed: Yes/No
- Alert Resolved: Yes/No
```

---

## Appendix C: Escalation Matrix

| Scenario | Escalation Level | Contact | SLA |
|----------|------------------|---------|-----|
| Consumer lag > 1000 | L2 - Platform Team | platform-oncall@ | 15 min |
| Database connection failures | L2 - Database Team | dba-oncall@ | 15 min |
| Schema validation failures | L1 - Application Team | app-oncall@ | 30 min |
| Producer failures | L1 - Application Team | app-oncall@ | 30 min |
| Multiple root causes | L3 - Engineering Manager | eng-manager@ | 30 min |
| Customer impact > 100 entities | L3 - Incident Commander | incident-commander@ | Immediate |

---

## Summary

This runbook provides a systematic approach to diagnosing and resolving Dead Letter Queue alerts:

1. **Discover** affected entities in the alert time window
2. **Analyze** processing status for each entity
3. **Investigate** consumer lag if entities are pending
4. **Search** DLQ for error details
5. **Determine** root cause using decision tree
6. **Remediate** based on root cause category
7. **Verify** resolution and monitor for recurrence
8. **Improve** system resilience based on learnings

**Expected Time to Resolution:** 2-5 minutes for common issues, up to 30 minutes for complex scenarios

**Automation Level:** Fully automated diagnostic steps with semi-automated remediation

---

*Last Updated: 2025-12-12*
*Version: 2.0 (Advanced)*
*Maintained by: SRE Team*

