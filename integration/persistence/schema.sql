BEGIN;
CREATE SCHEMA IF NOT EXISTS municipal;
CREATE TABLE IF NOT EXISTS municipal.tickets (
  tracking_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  report_id text NOT NULL UNIQUE CHECK (report_id ~ '^[A-Za-z0-9_-]{3,64}$'),
  input_sha256 text NOT NULL CHECK (length(input_sha256)=64),
  decision text NOT NULL CHECK (decision IN ('PASS','REVIEW','REJECT')),
  status text NOT NULL CHECK (status IN ('OPEN','NEEDS_REVIEW','IN_PROGRESS','RESOLVED','REJECTED')),
  payload jsonb NOT NULL,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS municipal.review_records (
  tracking_id uuid PRIMARY KEY REFERENCES municipal.tickets,
  reason_codes jsonb NOT NULL,
  policy jsonb NOT NULL,
  status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','RESOLVED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz
);
CREATE TABLE IF NOT EXISTS municipal.ticket_events (
  event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tracking_id uuid NOT NULL REFERENCES municipal.tickets,
  event text NOT NULL,
  actor text NOT NULL,
  details jsonb NOT NULL DEFAULT '{}',
  at timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION municipal.ticket_status(identifier text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,municipal,pg_temp AS $$
DECLARE t municipal.tickets;
BEGIN
  IF identifier IS NULL OR identifier !~ '^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$' THEN RETURN NULL; END IF;
  SELECT * INTO t FROM municipal.tickets WHERE tracking_id=identifier::uuid;
  IF NOT FOUND THEN RETURN NULL; END IF;
  RETURN jsonb_build_object('tracking_id',t.tracking_id,'report_id',t.report_id,'decision',t.decision,'status',t.status,
    'created_at',t.created_at,'updated_at',t.updated_at,'version',t.version,
    'category',t.payload->'category','severity',t.payload->'severity','department',t.payload->'department',
    'priority',t.payload->'priority','summary',t.payload->'summary','policy',t.payload->'policy',
    'review_reasons',t.payload->'review_reasons',
    'knowledge',jsonb_build_object('answer_found',t.payload#>'{knowledge,answer_found}',
      'verified',t.payload#>'{knowledge,verified}','procedure',t.payload#>'{knowledge,procedure}',
      'deadline',t.payload#>'{knowledge,deadline}','sources',t.payload#>'{knowledge,sources}'),
    'persisted',true,'review_queued',EXISTS(SELECT 1 FROM municipal.review_records WHERE tracking_id=t.tracking_id AND status='PENDING'));
END $$;

CREATE OR REPLACE FUNCTION municipal.save_report(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,municipal,pg_temp AS $$
DECLARE rid text:=p->>'report_id'; outcome text:=p->>'decision'; fingerprint text; t municipal.tickets; duplicate boolean:=false;
BEGIN
  IF jsonb_typeof(p) IS DISTINCT FROM 'object' OR rid IS NULL OR rid !~ '^[A-Za-z0-9_-]{3,64}$'
     OR outcome IS NULL OR outcome NOT IN ('PASS','REVIEW','REJECT')
     OR jsonb_typeof(p->'input_identity') IS DISTINCT FROM 'object'
     OR jsonb_typeof(p->'policy') IS DISTINCT FROM 'object'
     OR jsonb_typeof(p->'trace') IS DISTINCT FROM 'array'
     OR jsonb_typeof(p->'review_reasons') IS DISTINCT FROM 'array' THEN
    RAISE EXCEPTION 'INVALID_TICKET_PAYLOAD';
  END IF;
  IF outcome='PASS' AND (p#>>'{policy,gate_1,decision}' IS DISTINCT FROM 'PASS'
    OR p#>>'{policy,gate_2,decision}' IS DISTINCT FROM 'PASS' OR p#>>'{policy,gate_3,decision}' IS DISTINCT FROM 'PASS'
    OR jsonb_array_length(p->'review_reasons')<>0) THEN RAISE EXCEPTION 'UNVERIFIED_TICKET_CANNOT_AUTO_PASS'; END IF;
  IF coalesce(p#>>'{policy,gate_3,decision}','NOT_RUN')<>'PASS'
    AND (p#>'{knowledge,procedure}' IS DISTINCT FROM 'null'::jsonb OR p#>'{knowledge,deadline}' IS DISTINCT FROM 'null'::jsonb)
    THEN RAISE EXCEPTION 'UNVERIFIED_PROCEDURE_CANNOT_BE_PUBLISHED'; END IF;
  fingerprint=encode(sha256(convert_to((p->'input_identity')::text,'UTF8')),'hex');
  -- Serialize the same report ID, including concurrent initial submissions.
  PERFORM pg_advisory_xact_lock(hashtextextended(rid,0));
  SELECT * INTO t FROM municipal.tickets WHERE report_id=rid;
  IF FOUND THEN
    IF t.input_sha256<>fingerprint THEN RAISE EXCEPTION 'REPORT_ID_CONTENT_CONFLICT'; END IF;
    duplicate=true;
  ELSE
    INSERT INTO municipal.tickets(report_id,input_sha256,decision,status,payload)
    VALUES(rid,fingerprint,outcome,CASE outcome WHEN 'PASS' THEN 'OPEN' WHEN 'REJECT' THEN 'REJECTED' ELSE 'NEEDS_REVIEW' END,p-'input_identity')
    RETURNING * INTO t;
    IF outcome='REVIEW' THEN
      INSERT INTO municipal.review_records(tracking_id,reason_codes,policy) VALUES(t.tracking_id,p->'review_reasons',p->'policy');
    END IF;
    INSERT INTO municipal.ticket_events(tracking_id,event,actor,details)
    VALUES(t.tracking_id,'CREATED','n8n',jsonb_build_object('decision',outcome,'execution',p->'provenance'));
  END IF;
  RETURN municipal.ticket_status(t.tracking_id::text)||jsonb_build_object('deduplicated',duplicate);
END $$;

CREATE OR REPLACE FUNCTION municipal.change_status(identifier uuid,expected_version integer,next_status text,actor_name text,note text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,municipal,pg_temp AS $$
DECLARE t municipal.tickets;
BEGIN
  SELECT * INTO t FROM municipal.tickets WHERE tracking_id=identifier FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'TICKET_NOT_FOUND'; END IF;
  IF t.version IS DISTINCT FROM expected_version THEN RAISE EXCEPTION 'VERSION_CONFLICT'; END IF;
  IF actor_name IS NULL OR length(trim(actor_name))<1 OR length(actor_name)>100 OR note IS NULL OR length(trim(note))<5 THEN RAISE EXCEPTION 'ACTOR_AND_NOTE_REQUIRED'; END IF;
  IF next_status IS NULL OR NOT ((t.status='OPEN' AND next_status IN ('IN_PROGRESS','REJECTED'))
    OR (t.status='NEEDS_REVIEW' AND next_status IN ('OPEN','REJECTED'))
    OR (t.status='IN_PROGRESS' AND next_status IN ('RESOLVED','NEEDS_REVIEW')))
    THEN RAISE EXCEPTION 'INVALID_STATUS_TRANSITION'; END IF;
  UPDATE municipal.tickets SET status=next_status,version=version+1,updated_at=now() WHERE tracking_id=identifier;
  IF t.status='NEEDS_REVIEW' AND next_status IN ('OPEN','REJECTED') THEN
    UPDATE municipal.review_records SET status='RESOLVED',resolved_at=now() WHERE tracking_id=identifier;
  ELSIF next_status='NEEDS_REVIEW' THEN
    INSERT INTO municipal.review_records(tracking_id,reason_codes,policy) VALUES(identifier,jsonb_build_array('STAFF_REVIEW_REQUESTED'),t.payload->'policy')
    ON CONFLICT(tracking_id) DO UPDATE SET status='PENDING',resolved_at=NULL;
  END IF;
  INSERT INTO municipal.ticket_events(tracking_id,event,actor,details) VALUES(identifier,'STATUS_CHANGED',actor_name,
    jsonb_build_object('from',t.status,'to',next_status,'note',note));
  RETURN municipal.ticket_status(identifier::text);
END $$;
REVOKE ALL ON SCHEMA municipal FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA municipal FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA municipal FROM PUBLIC;
COMMIT;
