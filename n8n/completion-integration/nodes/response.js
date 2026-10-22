const x=$input.first().json;
return [{json:{report_id:x.report_id,workflow_status:x.workflow_status,decision:x.decision,
  ticket:x.ticket,policy:x.ticket?.policy||x.policy,review_reasons:x.ticket?.review_reasons||[...new Set(x.review_reasons)],
  errors:x.errors,components:x.components,trace:x.trace,
  visual_assessment:{...x.visual_assessment,category:x.ticket?.category||null,severity:x.ticket?.severity||null},
  routing:{department:x.ticket?.department||null,priority:x.ticket?.priority||null},
  knowledge:x.ticket?.knowledge||null,persisted:x.persisted,review_queued:x.review_queued,
  deployment:{orchestrator:'municipal-completion-v1'},
  notice:x.persisted?'Processing completed and the ticket was committed to PostgreSQL. Review flags remain attached; no manual step is needed to finish processing.':'Database persistence failed or could not be confirmed. No ticket creation is claimed.',
  http_status:x.persisted?(x.decision==='REJECT'?422:200):503}}];
