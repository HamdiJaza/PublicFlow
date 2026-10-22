const x=$input.first().json;
const decision=x.decision==='REJECT'?'REJECT':'REVIEW';
return [{json:{report_id:x.report_id,decision,ticket:null,policy:x.policy,
  review_reasons:[...new Set(x.review_reasons||[])],errors:[...new Set(x.errors||[])],
  components:x.components,trace:x.trace,audit:x.audit,
  deployment:{orchestrator:'intake-integration-v1',intake_source_sha256:x.integration.local_source_sha256},
  persisted:false,review_queued:false,
  notice:'Intake development integration only. Downstream agents and ticket storage were not called. REVIEW is not a persisted review queue entry.',
  http_status:decision==='REJECT'?422:202}}];
