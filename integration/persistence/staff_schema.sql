-- Staff console: organisations, ticket ownership and scoped staff actions.
-- Additive and idempotent; schema.sql objects and existing tickets are preserved.
-- Applied after schema.sql by setup.py --initialize.
BEGIN;
CREATE TABLE IF NOT EXISTS municipal.organisations (
  code text PRIMARY KEY CHECK (code ~ '^[A-Z][A-Z0-9_]{1,39}$'),
  kind text NOT NULL CHECK (kind IN ('MUNICIPALITY','UTILITY')),
  name_fr text NOT NULL CHECK (length(btrim(name_fr)) BETWEEN 2 AND 120),
  name_ar text CHECK (name_ar IS NULL OR length(name_ar) <= 120),
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);
-- Region groups communes in the citizen form (e.g. GRAND_TUNIS); labels live in the UI.
ALTER TABLE municipal.organisations ADD COLUMN IF NOT EXISTS region text CHECK (region IS NULL OR region ~ '^[A-Z][A-Z_]{1,39}$');
-- The application is in English: name_en is displayed, name_fr stays the official name.
ALTER TABLE municipal.organisations ADD COLUMN IF NOT EXISTS name_en text CHECK (name_en IS NULL OR length(btrim(name_en)) BETWEEN 2 AND 120);
-- Grand Tunis communes requested for the demo. The RAG corpus covers only Commune de Tunis:
-- tickets from other communes get no verified procedure (REVIEW), never an invented one.
INSERT INTO municipal.organisations(code,kind,name_fr,name_ar,name_en,region) VALUES
  ('COMMUNE_TUNIS','MUNICIPALITY','Commune de Tunis','بلدية تونس','Municipality of Tunis','GRAND_TUNIS'),
  ('COMMUNE_ARIANA','MUNICIPALITY','Commune de l''Ariana','بلدية أريانة','Municipality of Ariana','GRAND_TUNIS'),
  ('COMMUNE_BEN_AROUS','MUNICIPALITY','Commune de Ben Arous','بلدية بن عروس','Municipality of Ben Arous','GRAND_TUNIS'),
  ('STEG','UTILITY','STEG (électricité et gaz)','الشركة التونسية للكهرباء والغاز','STEG (electricity and gas)',NULL),
  ('SONEDE','UTILITY','SONEDE (eau potable)','الشركة الوطنية لاستغلال وتوزيع المياه','SONEDE (drinking water)',NULL)
-- Fill only what is missing, so an administrator's later edits are kept.
ON CONFLICT (code) DO UPDATE SET region=coalesce(municipal.organisations.region,EXCLUDED.region),
  name_en=coalesce(municipal.organisations.name_en,EXCLUDED.name_en);

-- commune: the citizen's municipality, which supervises the ticket.
-- organisation: who executes the work (the commune itself, STEG or SONEDE).
ALTER TABLE municipal.tickets ADD COLUMN IF NOT EXISTS commune text REFERENCES municipal.organisations(code);
ALTER TABLE municipal.tickets ADD COLUMN IF NOT EXISTS organisation text REFERENCES municipal.organisations(code);
CREATE INDEX IF NOT EXISTS tickets_commune_status ON municipal.tickets(commune,status,updated_at);
CREATE INDEX IF NOT EXISTS tickets_organisation_status ON municipal.tickets(organisation,status,updated_at);
CREATE INDEX IF NOT EXISTS ticket_events_ticket ON municipal.ticket_events(tracking_id,at);

-- Ownership comes from the workflow payload (Department Rules); nothing is inferred here.
-- A missing commune falls back to the demo municipality and the fallback is recorded.
CREATE OR REPLACE FUNCTION municipal.route_ticket() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,municipal,pg_temp AS $$
DECLARE c text:=NEW.payload#>>'{location,commune}'; o text:=NEW.payload->>'organisation'; source text:='citizen';
BEGIN
  IF c IS NULL OR NOT EXISTS(SELECT 1 FROM municipal.organisations WHERE code=c AND kind='MUNICIPALITY' AND active) THEN
    c:='COMMUNE_TUNIS'; source:='default';
  END IF;
  -- Department Rules sends this token for work done by the commune's own services.
  IF o='SUPERVISING_COMMUNE' THEN o:=c; END IF;
  IF o IS NOT NULL AND NOT EXISTS(SELECT 1 FROM municipal.organisations WHERE code=o AND active) THEN o:=NULL; END IF;
  -- A commune only executes its own tickets.
  IF o IS NOT NULL AND o<>c AND EXISTS(SELECT 1 FROM municipal.organisations WHERE code=o AND kind='MUNICIPALITY') THEN o:=c; END IF;
  NEW.commune:=c; NEW.organisation:=o;
  NEW.payload:=NEW.payload||jsonb_build_object('staff_routing',jsonb_build_object('commune_source',source,
    'organisation_source',CASE WHEN o IS NULL THEN 'unassigned' ELSE 'workflow' END));
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS tickets_route ON municipal.tickets;
CREATE TRIGGER tickets_route BEFORE INSERT ON municipal.tickets FOR EACH ROW EXECUTE FUNCTION municipal.route_ticket();

-- One-off backfill for tickets saved before this migration (category to owner, as Department Rules).
UPDATE municipal.tickets SET commune='COMMUNE_TUNIS' WHERE commune IS NULL;
UPDATE municipal.tickets SET organisation=CASE payload->>'category'
    WHEN 'ROAD_DAMAGE' THEN commune WHEN 'WASTE' THEN commune
    WHEN 'STREET_LIGHTING' THEN 'STEG' WHEN 'WATER_LEAK' THEN 'SONEDE' END
  WHERE organisation IS NULL AND payload->>'category' IS NOT NULL;

CREATE OR REPLACE FUNCTION municipal.organisation_name(c text) RETURNS text
LANGUAGE sql STABLE SET search_path=pg_catalog,municipal,pg_temp AS $$
  SELECT coalesce(name_en,name_fr) FROM municipal.organisations WHERE code=c $$;

-- Citizen view: no agent names, internal notes or execution traces.
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
    'summary_en',t.payload#>'{summary_translation,en}',
    'review_reasons',t.payload->'review_reasons',
    'commune',t.commune,'commune_name',municipal.organisation_name(t.commune),
    'organisation',t.organisation,'organisation_name',municipal.organisation_name(t.organisation),    'timeline',(SELECT coalesce(jsonb_agg(jsonb_build_object('at',e.at,
        'status',coalesce(e.details->>'to',CASE e.details->>'decision' WHEN 'PASS' THEN 'OPEN' WHEN 'REJECT' THEN 'REJECTED' ELSE 'NEEDS_REVIEW' END),
        'message',e.details->'public_note') ORDER BY e.at,e.event_id),'[]'::jsonb)
      FROM municipal.ticket_events e WHERE e.tracking_id=t.tracking_id AND e.event IN ('CREATED','STATUS_CHANGED','REVIEWED','ASSIGNED')),
    'knowledge',jsonb_build_object('answer_found',t.payload#>'{knowledge,answer_found}',
      'verified',t.payload#>'{knowledge,verified}','procedure',t.payload#>'{knowledge,procedure}',
      'deadline',t.payload#>'{knowledge,deadline}','sources',t.payload#>'{knowledge,sources}'),
    'persisted',true,'review_queued',EXISTS(SELECT 1 FROM municipal.review_records WHERE tracking_id=t.tracking_id AND status='PENDING'));
END $$;

CREATE OR REPLACE FUNCTION municipal.staff_ticket_row(t municipal.tickets) RETURNS jsonb
LANGUAGE sql STABLE SET search_path=pg_catalog,municipal,pg_temp AS $$
  SELECT jsonb_build_object('tracking_id',t.tracking_id,'status',t.status,'decision',t.decision,'version',t.version,
    'category',t.payload->'category','severity',t.payload->'severity','priority',t.payload->'priority',
    'summary',left(coalesce(t.payload->>'summary',''),180),'address',t.payload#>'{location,address}',
    'commune',t.commune,'organisation',t.organisation,'organisation_name',municipal.organisation_name(t.organisation),
    'review_reasons',coalesce(t.payload->'review_reasons','[]'::jsonb),'created_at',t.created_at,'updated_at',t.updated_at) $$;

CREATE OR REPLACE FUNCTION municipal.staff_ticket_detail(t municipal.tickets) RETURNS jsonb
LANGUAGE sql STABLE SET search_path=pg_catalog,municipal,pg_temp AS $$
  SELECT municipal.staff_ticket_row(t)||jsonb_build_object(
    'summary',t.payload->'summary','report_id',t.report_id,'department',t.payload->'department','location',t.payload->'location',
    'commune_name',municipal.organisation_name(t.commune),'ai_classification',t.payload->'ai_classification',
    'gates',jsonb_build_object(
      'gate_1',jsonb_build_object('decision',t.payload#>'{policy,gate_1,decision}','reason_codes',t.payload#>'{policy,gate_1,reason_codes}'),
      'gate_2',jsonb_build_object('decision',t.payload#>'{policy,gate_2,decision}','reason_codes',t.payload#>'{policy,gate_2,reason_codes}'),
      'gate_3',jsonb_build_object('decision',t.payload#>'{policy,gate_3,decision}','reason_codes',t.payload#>'{policy,gate_3,reason_codes}')),
    'vision',(SELECT jsonb_agg(jsonb_build_object('description',f#>'{native,description}','evidence',f#>'{native,evidence}',
        'confidence',f#>'{native,confidence}','uncertainty_reason',f#>'{native,uncertainty_reason}',
        'text_image_consistent',f#>'{native,text_image_consistent}'))
      FROM jsonb_array_elements(CASE jsonb_typeof(t.payload->'vision_frames') WHEN 'array' THEN t.payload->'vision_frames' ELSE '[]'::jsonb END) f),
    -- English machine translation of the French summary, for display; the summary stays authoritative.
    'summary_translation',t.payload->'summary_translation',
    'knowledge',jsonb_build_object('verified',t.payload#>'{knowledge,verified}','procedure',t.payload#>'{knowledge,procedure}',
      'sources',t.payload#>'{knowledge,sources}'),
    'review',(SELECT jsonb_build_object('status',r.status,'reason_codes',r.reason_codes,'created_at',r.created_at,'resolved_at',r.resolved_at)
      FROM municipal.review_records r WHERE r.tracking_id=t.tracking_id),
    'events',(SELECT coalesce(jsonb_agg(jsonb_build_object('at',e.at,'event',e.event,'actor',e.actor,
        'from',e.details->'from','to',e.details->'to','note',e.details->'note','public_note',e.details->'public_note',
        'organisation',e.details->'organisation','corrections',e.details->'corrections') ORDER BY e.at,e.event_id),'[]'::jsonb)
      FROM municipal.ticket_events e WHERE e.tracking_id=t.tracking_id)) $$;

-- Who may see a ticket: the supervising commune sees all of its tickets;
-- STEG/SONEDE see only work assigned to them and not under review.
CREATE OR REPLACE FUNCTION municipal.staff_can_see(t municipal.tickets,actor_role text,actor_org text) RETURNS boolean
LANGUAGE sql STABLE SET search_path=pg_catalog,municipal,pg_temp AS $$
  SELECT CASE actor_role
    WHEN 'MUNICIPALITY' THEN t.commune=actor_org
    WHEN 'UTILITY' THEN t.organisation=actor_org AND t.status IN ('OPEN','IN_PROGRESS','RESOLVED')
    ELSE false END $$;

-- Public list for the citizen form: names only.
CREATE OR REPLACE FUNCTION municipal.public_communes() RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,municipal,pg_temp AS $$
  SELECT coalesce(jsonb_agg(jsonb_build_object('code',code,'name_fr',name_fr,'name_ar',name_ar,'name_en',name_en,'region',region)
    ORDER BY region,coalesce(name_en,name_fr)),'[]'::jsonb)
  FROM municipal.organisations WHERE kind='MUNICIPALITY' AND active $$;

-- Business failures RAISE a code and roll back; staff_api turns them into {ok:false,error}.
CREATE OR REPLACE FUNCTION municipal.staff_api_inner(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,municipal,pg_temp AS $$
DECLARE
  act text:=p->>'action'; actor_role text:=p#>>'{actor,role}'; actor_org text:=p#>>'{actor,organisation}';
  who text:=btrim(coalesce(p#>>'{actor,name}',''));
  note text:=nullif(btrim(coalesce(p->>'note','')),''); public_note text:=nullif(btrim(coalesce(p->>'public_note','')),'');
  t municipal.tickets; target text; next_status text; category text; severity text; corrections jsonb:='{}'::jsonb;
  executor boolean; filter text:=p->>'status';
BEGIN
  IF act IS NULL OR length(who) NOT BETWEEN 1 AND 100 OR length(coalesce(note,'')) > 2000 OR length(coalesce(public_note,'')) > 500 THEN
    RAISE EXCEPTION 'STAFF_REQUEST_INVALID';
  END IF;

  -- Maintenance engineer: organisation catalogue and anonymous counts, never ticket content.
  IF actor_role='ADMIN' THEN
    IF act='organisations' THEN
      RETURN jsonb_build_object('ok',true,'organisations',(SELECT coalesce(jsonb_agg(to_jsonb(o) ORDER BY o.kind,o.name_fr),'[]'::jsonb) FROM municipal.organisations o));
    ELSIF act='add_commune' THEN
      target:=p->>'code';
      IF target IS NULL OR target !~ '^COMMUNE_[A-Z0-9_]{2,31}$' OR length(btrim(coalesce(p->>'name_fr',''))) NOT BETWEEN 2 AND 120
         OR length(btrim(coalesce(p->>'name_en',''))) NOT BETWEEN 2 AND 120
         OR length(coalesce(p->>'name_ar','')) > 120 OR coalesce(p->>'region','GRAND_TUNIS') !~ '^[A-Z][A-Z_]{1,39}$' THEN RAISE EXCEPTION 'COMMUNE_INVALID'; END IF;
      IF EXISTS(SELECT 1 FROM municipal.organisations WHERE code=target) THEN RAISE EXCEPTION 'COMMUNE_EXISTS'; END IF;
      INSERT INTO municipal.organisations(code,kind,name_fr,name_ar,name_en,region)
      VALUES(target,'MUNICIPALITY',btrim(p->>'name_fr'),nullif(btrim(coalesce(p->>'name_ar','')),''),btrim(p->>'name_en'),nullif(p->>'region',''));
      RETURN jsonb_build_object('ok',true,'code',target);
    ELSIF act='set_active' THEN
      target:=p->>'code';
      IF target IN ('COMMUNE_TUNIS','STEG','SONEDE') THEN RAISE EXCEPTION 'ORGANISATION_LOCKED'; END IF;
      UPDATE municipal.organisations SET active=(p->>'active')::boolean WHERE code=target AND kind='MUNICIPALITY';
      IF NOT FOUND THEN RAISE EXCEPTION 'ORGANISATION_NOT_FOUND'; END IF;
      RETURN jsonb_build_object('ok',true);
    ELSIF act='overview' THEN
      RETURN jsonb_build_object('ok',true,
        'by_status',(SELECT coalesce(jsonb_object_agg(status,n),'{}'::jsonb) FROM (SELECT status,count(*) n FROM municipal.tickets GROUP BY status) s),
        'by_organisation',(SELECT coalesce(jsonb_agg(jsonb_build_object('organisation',coalesce(organisation,'UNASSIGNED'),'status',status,'count',n)),'[]'::jsonb)
          FROM (SELECT organisation,status,count(*) n FROM municipal.tickets GROUP BY organisation,status) s),
        'total',(SELECT count(*) FROM municipal.tickets),'last_ticket_at',(SELECT max(created_at) FROM municipal.tickets));
    END IF;
    RAISE EXCEPTION 'STAFF_ACTION_FORBIDDEN';
  END IF;

  IF actor_role NOT IN ('MUNICIPALITY','UTILITY') OR NOT EXISTS(SELECT 1 FROM municipal.organisations o
      WHERE o.code=actor_org AND o.active AND o.kind=CASE actor_role WHEN 'MUNICIPALITY' THEN 'MUNICIPALITY' ELSE 'UTILITY' END) THEN
    RAISE EXCEPTION 'STAFF_ACTOR_INVALID';
  END IF;

  IF act='organisations' THEN
    RETURN jsonb_build_object('ok',true,'organisations',(SELECT coalesce(jsonb_agg(jsonb_build_object('code',o.code,'kind',o.kind,'name_fr',o.name_fr,'name_en',o.name_en) ORDER BY o.kind,coalesce(o.name_en,o.name_fr)),'[]'::jsonb)
      FROM municipal.organisations o WHERE o.active AND (o.kind='UTILITY' OR o.code=actor_org)));
  END IF;
  IF act='list' THEN
    IF filter IS NOT NULL AND filter NOT IN ('OPEN','NEEDS_REVIEW','IN_PROGRESS','RESOLVED','REJECTED') THEN RAISE EXCEPTION 'STAFF_REQUEST_INVALID'; END IF;
    RETURN jsonb_build_object('ok',true,
      'tickets',(SELECT coalesce(jsonb_agg(municipal.staff_ticket_row(x) ORDER BY x.updated_at DESC),'[]'::jsonb) FROM
        (SELECT * FROM municipal.tickets k WHERE municipal.staff_can_see(k,actor_role,actor_org) AND (filter IS NULL OR k.status=filter)
         ORDER BY k.updated_at DESC LIMIT 200) x),
      'counts',(SELECT coalesce(jsonb_object_agg(status,n),'{}'::jsonb) FROM
        (SELECT k.status,count(*) n FROM municipal.tickets k WHERE municipal.staff_can_see(k,actor_role,actor_org) GROUP BY k.status) s));
  END IF;

  IF coalesce(p->>'tracking_id','') !~ '^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$' THEN RAISE EXCEPTION 'TICKET_NOT_FOUND'; END IF;
  SELECT * INTO t FROM municipal.tickets WHERE tracking_id=(p->>'tracking_id')::uuid FOR UPDATE;
  -- Invisible tickets are reported as missing so other organisations' tickets cannot be probed.
  IF NOT FOUND OR NOT municipal.staff_can_see(t,actor_role,actor_org) THEN RAISE EXCEPTION 'TICKET_NOT_FOUND'; END IF;
  IF act='detail' THEN RETURN jsonb_build_object('ok',true,'ticket',municipal.staff_ticket_detail(t)); END IF;

  IF act='comment' THEN
    IF note IS NULL OR length(note)<2 THEN RAISE EXCEPTION 'NOTE_REQUIRED'; END IF;
    INSERT INTO municipal.ticket_events(tracking_id,event,actor,details) VALUES(t.tracking_id,'COMMENT',who,jsonb_build_object('note',note,'organisation',actor_org));
    SELECT * INTO t FROM municipal.tickets WHERE tracking_id=t.tracking_id;
    RETURN jsonb_build_object('ok',true,'ticket',municipal.staff_ticket_detail(t));
  END IF;

  -- Every state change is version-checked and needs a note for the audit trail.
  IF (p->>'expected_version') IS NULL OR (p->>'expected_version')::integer IS DISTINCT FROM t.version THEN RAISE EXCEPTION 'VERSION_CONFLICT'; END IF;
  IF note IS NULL OR length(note)<5 THEN RAISE EXCEPTION 'NOTE_REQUIRED'; END IF;
  executor:=t.organisation=actor_org;

  IF act IN ('approve','reassign') THEN
    IF actor_role<>'MUNICIPALITY' THEN RAISE EXCEPTION 'STAFF_ACTION_FORBIDDEN'; END IF;
    IF (act='approve' AND t.status<>'NEEDS_REVIEW') OR (act='reassign' AND t.status NOT IN ('OPEN','IN_PROGRESS')) THEN RAISE EXCEPTION 'INVALID_STATUS_TRANSITION'; END IF;
    target:=p->>'organisation';
    -- A commune assigns to its own services or to a national utility, never to another commune.
    IF target IS NULL OR NOT EXISTS(SELECT 1 FROM municipal.organisations o WHERE o.code=target AND o.active AND (o.kind='UTILITY' OR o.code=actor_org)) THEN
      RAISE EXCEPTION 'ORGANISATION_INVALID';
    END IF;
    category:=coalesce(p->>'category',t.payload->>'category'); severity:=coalesce(p->>'severity',t.payload->>'severity');
    IF category IS NULL OR category NOT IN ('ROAD_DAMAGE','STREET_LIGHTING','WASTE','WATER_LEAK')
       OR severity IS NULL OR severity NOT IN ('LOW','MEDIUM','HIGH') THEN RAISE EXCEPTION 'CLASSIFICATION_INVALID'; END IF;
    IF category IS DISTINCT FROM t.payload->>'category' THEN corrections:=corrections||jsonb_build_object('category',jsonb_build_object('from',t.payload->'category','to',category)); END IF;
    IF severity IS DISTINCT FROM t.payload->>'severity' THEN corrections:=corrections||jsonb_build_object('severity',jsonb_build_object('from',t.payload->'severity','to',severity)); END IF;
    -- The AI output is kept once, unchanged, beside the human correction.
    UPDATE municipal.tickets SET organisation=target,status='OPEN',version=version+1,updated_at=now(),
      payload=CASE WHEN payload ? 'ai_classification' THEN payload ELSE payload||jsonb_build_object('ai_classification',jsonb_build_object(
          'category',payload->'category','severity',payload->'severity','department',payload->'department','priority',payload->'priority')) END
        ||jsonb_build_object('category',category,'severity',severity,'priority',severity,
          -- Mirrors Department Rules in the n8n workflow (severity_to_priority_v1 for priority).
          'department',CASE category WHEN 'ROAD_DAMAGE' THEN 'ROADS_DEPARTMENT' WHEN 'STREET_LIGHTING' THEN 'PUBLIC_LIGHTING_DEPARTMENT'
            WHEN 'WASTE' THEN 'SANITATION_DEPARTMENT' WHEN 'WATER_LEAK' THEN 'WATER_SERVICES_DEPARTMENT' END)
      WHERE tracking_id=t.tracking_id;
    UPDATE municipal.review_records SET status='RESOLVED',resolved_at=now() WHERE tracking_id=t.tracking_id AND status='PENDING';
    INSERT INTO municipal.ticket_events(tracking_id,event,actor,details) VALUES(t.tracking_id,CASE act WHEN 'approve' THEN 'REVIEWED' ELSE 'ASSIGNED' END,who,
      jsonb_build_object('from',t.status,'to','OPEN','organisation',target,'corrections',corrections,'note',note,'public_note',public_note));
  ELSE
    next_status:=CASE
      WHEN act='reject' AND actor_role='MUNICIPALITY' AND t.status IN ('NEEDS_REVIEW','OPEN') THEN 'REJECTED'
      WHEN act='start' AND executor AND t.status='OPEN' THEN 'IN_PROGRESS'
      WHEN act='done' AND executor AND t.status='IN_PROGRESS' THEN 'RESOLVED'
      -- "Not done" always returns the ticket to the supervising commune.
      WHEN act='not_done' AND executor AND t.status IN ('OPEN','IN_PROGRESS') THEN 'NEEDS_REVIEW'
      WHEN act='reopen' AND actor_role='MUNICIPALITY' AND t.status='RESOLVED' THEN 'NEEDS_REVIEW' END;
    IF next_status IS NULL THEN
      IF act NOT IN ('reject','start','done','not_done','reopen') THEN RAISE EXCEPTION 'STAFF_REQUEST_INVALID'; END IF;
      RAISE EXCEPTION 'INVALID_STATUS_TRANSITION';
    END IF;
    UPDATE municipal.tickets SET status=next_status,version=version+1,updated_at=now() WHERE tracking_id=t.tracking_id;
    IF next_status='NEEDS_REVIEW' THEN
      INSERT INTO municipal.review_records(tracking_id,reason_codes,policy)
      VALUES(t.tracking_id,jsonb_build_array(CASE act WHEN 'reopen' THEN 'REOPENED_BY_MUNICIPALITY' ELSE 'EXECUTION_NOT_DONE' END),t.payload->'policy')
      ON CONFLICT(tracking_id) DO UPDATE SET status='PENDING',resolved_at=NULL,reason_codes=EXCLUDED.reason_codes;
    ELSIF next_status='REJECTED' THEN
      UPDATE municipal.review_records SET status='RESOLVED',resolved_at=now() WHERE tracking_id=t.tracking_id AND status='PENDING';
    END IF;
    INSERT INTO municipal.ticket_events(tracking_id,event,actor,details) VALUES(t.tracking_id,'STATUS_CHANGED',who,
      jsonb_build_object('from',t.status,'to',next_status,'note',note,'public_note',public_note,'organisation',actor_org));
  END IF;
  SELECT * INTO t FROM municipal.tickets WHERE tracking_id=t.tracking_id;
  RETURN jsonb_build_object('ok',true,'ticket',municipal.staff_ticket_detail(t));
END $$;

CREATE OR REPLACE FUNCTION municipal.staff_api(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,municipal,pg_temp AS $$
BEGIN
  IF jsonb_typeof(p) IS DISTINCT FROM 'object' THEN RETURN jsonb_build_object('ok',false,'error','STAFF_REQUEST_INVALID'); END IF;
  RETURN municipal.staff_api_inner(p);
EXCEPTION
  -- Known codes only; anything else is reported generically without SQL details.
  WHEN raise_exception THEN
    RETURN jsonb_build_object('ok',false,'error',CASE WHEN SQLERRM ~ '^[A-Z_]{5,40}$' THEN SQLERRM ELSE 'STAFF_REQUEST_FAILED' END);
  WHEN invalid_text_representation OR numeric_value_out_of_range THEN
    RETURN jsonb_build_object('ok',false,'error','STAFF_REQUEST_INVALID');
END $$;

REVOKE ALL ON ALL TABLES IN SCHEMA municipal FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA municipal FROM PUBLIC;
COMMIT;
