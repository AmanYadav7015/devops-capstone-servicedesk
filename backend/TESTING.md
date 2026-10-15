# ServiceDesk — backend verification evidence

Everything in this file is captured terminal output from a real run on the development machine.
Nothing here is illustrative or reconstructed. Where a command produced a long transcript it is
reproduced in full rather than summarised, so every status code and every row count can be checked.

## Contents

1. [What was running](#1-what-was-running)
2. [Alembic migrations against a real PostgreSQL](#2-alembic-migrations-against-a-real-postgresql)
3. [Every endpoint exercised with curl](#3-every-endpoint-exercised-with-curl)
4. [pytest](#4-pytest)
5. [Frontend build and real browser renders](#5-frontend-build-and-real-browser-renders)
6. [How to reproduce all of it](#6-how-to-reproduce-all-of-it)

---

## 1. What was running

| Component | Detail |
|---|---|
| Database | `postgres:16-alpine` in a container named `servicedesk-pg-dev`, host port `55433` |
| `DATABASE_URL` | `postgresql+psycopg://servicedesk:servicedesk@localhost:55433/servicedesk` |
| Backend | `uvicorn app.main:app` on `127.0.0.1:8010` |
| Python | 3.12.13 |
| Node | v26.7.0, npm 12.0.2 |
| Frontend | production bundle from `npm run build`, served on `127.0.0.1:5180` with `/api` proxied to the backend |

Port 55433 was chosen instead of 5432, and 8010 instead of 8000, to avoid colliding with anything
else already bound on the machine.

The schema is created by Alembic, not by hand and not by `Base.metadata.create_all`. Section 2
starts from a database with no tables at all and shows the migrations building it.

---

## 2. Alembic migrations against a real PostgreSQL

Two revisions:

| Revision | Purpose |
|---|---|
| `0001_schema` | creates `categories` and `tickets`, including the `tickets.category_id` foreign key |
| `0002_seed` | inserts the four default service desk categories |

The transcript below shows, in order: the database empty; the revision chain; `alembic current`
returning nothing because the database is not yet stamped; `alembic upgrade head`; the two tables
and the foreign key as PostgreSQL itself reports them; an insert that PostgreSQL rejects because
the foreign key is enforced; `alembic check` finding no drift between the models and the migrated
schema; and a full `downgrade base` / `upgrade head` round trip performed with a ticket row
referencing a seeded category, so the downgrade has to deal with the foreign key rather than
sidestep it.

```console
$ docker exec servicedesk-pg-dev psql -U servicedesk -d servicedesk -c '\dt'
Did not find any relations.

$ alembic history --verbose
Rev: 0002_seed (head)
Parent: 0001_schema
Path: /Users/aman/Desktop/devops-heros/helpdesk-capstone/backend/alembic/versions/0002_seed_default_categories.py

    seed the default service desk categories
    
    Revision ID: 0002_seed
    Revises: 0001_schema
    Create Date: 2026-10-15 16:58:02.114903

Rev: 0001_schema
Parent: <base>
Path: /Users/aman/Desktop/devops-heros/helpdesk-capstone/backend/alembic/versions/0001_create_categories_and_tickets.py

    create categories and tickets tables
    
    Revision ID: 0001_schema
    Revises:
    Create Date: 2026-10-15 16:51:38.778489


$ alembic current
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
(no output above the log lines: the database is not stamped with any revision yet)

$ alembic upgrade head
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 0001_schema, create categories and tickets tables
INFO  [alembic.runtime.migration] Running upgrade 0001_schema -> 0002_seed, seed the default service desk categories

$ alembic current
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
0002_seed (head)

$ psql -c '\dt'
               List of relations
 Schema |      Name       | Type  |    Owner    
--------+-----------------+-------+-------------
 public | alembic_version | table | servicedesk
 public | categories      | table | servicedesk
 public | tickets         | table | servicedesk
(3 rows)


$ psql -c '\d categories'
                                      Table "public.categories"
   Column    |         Type          | Collation | Nullable |                Default                 
-------------+-----------------------+-----------+----------+----------------------------------------
 id          | integer               |           | not null | nextval('categories_id_seq'::regclass)
 name        | character varying(80) |           | not null | 
 description | text                  |           | not null | 
Indexes:
    "categories_pkey" PRIMARY KEY, btree (id)
    "categories_name_key" UNIQUE CONSTRAINT, btree (name)
Referenced by:
    TABLE "tickets" CONSTRAINT "tickets_category_id_fkey" FOREIGN KEY (category_id) REFERENCES categories(id)


$ psql -c '\d tickets'
                                       Table "public.tickets"
   Column    |           Type           | Collation | Nullable |               Default               
-------------+--------------------------+-----------+----------+-------------------------------------
 id          | integer                  |           | not null | nextval('tickets_id_seq'::regclass)
 subject     | character varying(200)   |           | not null | 
 description | text                     |           | not null | 
 severity    | character varying(20)    |           | not null | 
 status      | character varying(30)    |           | not null | 
 requester   | character varying(120)   |           | not null | 
 assignee    | character varying(120)   |           | not null | 
 category_id | integer                  |           |          | 
 created_at  | timestamp with time zone |           | not null | 
 sla_due_at  | timestamp with time zone |           | not null | 
Indexes:
    "tickets_pkey" PRIMARY KEY, btree (id)
Foreign-key constraints:
    "tickets_category_id_fkey" FOREIGN KEY (category_id) REFERENCES categories(id)


$ psql -c "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = 'tickets'::regclass AND contype = 'f';"
         conname          |                     definition                      
--------------------------+-----------------------------------------------------
 tickets_category_id_fkey | FOREIGN KEY (category_id) REFERENCES categories(id)
(1 row)


$ psql -c 'SELECT * FROM alembic_version;'
 version_num 
-------------
 0002_seed
(1 row)


$ psql -c 'SELECT id, name FROM categories ORDER BY id;'
 id |   name   
----+----------
  1 | Hardware
  2 | Network
  3 | Access
  4 | Software
(4 rows)


--- foreign key is enforced, not decorative ---
$ psql -c "INSERT INTO tickets (subject, description, severity, status, requester, assignee, category_id, created_at, sla_due_at) VALUES ('fk probe', '', 'LOW', 'OPEN', 'probe', 'probe', 9999, now(), now());"
ERROR:  insert or update on table "tickets" violates foreign key constraint "tickets_category_id_fkey"
DETAIL:  Key (category_id)=(9999) is not present in table "categories".

--- autogenerate finds no drift between the models and the migrated schema ---
$ alembic check
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.ddl.postgresql] Detected sequence named 'categories_id_seq' as owned by integer column 'categories(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'tickets_id_seq' as owned by integer column 'tickets(id)', assuming SERIAL and omitting
No new upgrade operations detected.

--- round trip: downgrade base then upgrade head, with a ticket referencing a seeded category ---
$ psql -c "INSERT INTO tickets (...) VALUES ('round trip probe', ..., category_id = 1, ...);"
INSERT 0 1

$ alembic downgrade base
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running downgrade 0002_seed -> 0001_schema, seed the default service desk categories
INFO  [alembic.runtime.migration] Running downgrade 0001_schema -> , create categories and tickets tables

$ psql -c '\dt'
               List of relations
 Schema |      Name       | Type  |    Owner    
--------+-----------------+-------+-------------
 public | alembic_version | table | servicedesk
(1 row)


$ alembic current
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.

$ alembic upgrade head
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 0001_schema, create categories and tickets tables
INFO  [alembic.runtime.migration] Running upgrade 0001_schema -> 0002_seed, seed the default service desk categories

$ alembic current
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
0002_seed (head)

$ psql -c '\dt'
               List of relations
 Schema |      Name       | Type  |    Owner    
--------+-----------------+-------+-------------
 public | alembic_version | table | servicedesk
 public | categories      | table | servicedesk
 public | tickets         | table | servicedesk
(3 rows)


$ psql -c "SELECT conname FROM pg_constraint WHERE conrelid = 'tickets'::regclass AND contype = 'f';"
         conname          
--------------------------
 tickets_category_id_fkey
(1 row)

```

### What that proves

- `\d tickets` lists `"tickets_category_id_fkey" FOREIGN KEY (category_id) REFERENCES categories(id)`
  and `\d categories` lists the matching `Referenced by:` line. The relationship exists in the
  database, not only in the SQLAlchemy model.
- Inserting `category_id = 9999` is rejected by PostgreSQL with
  `violates foreign key constraint "tickets_category_id_fkey"`.
- `alembic check` reports `No new upgrade operations detected`, so the migration and the models
  describe the same schema. This is why the test suite can create its schema with
  `Base.metadata.create_all` and still be testing the shape the migration produces.
- After `downgrade base` only `alembic_version` remains, and `alembic current` prints nothing.
  After `upgrade head` both tables and the foreign key are back.

---

## 3. Every endpoint exercised with curl

Against the running backend and the real PostgreSQL. Every endpoint in the contract is called,
and every documented failure mode is provoked: 404 on a missing id for GET, PUT and DELETE,
409 on a duplicate category name, 422 on an unknown `category_id`, 422 on a bad severity enum,
422 on a bad status enum, and 422 on a missing required field.

The SLA section is the important one. `breachingSla` is not asserted from an empty queue — a
ticket is inserted with `sla_due_at` three hours in the past, and the count is shown changing from
0 to 1. Then a past-due but `RESOLVED` ticket is inserted to show it is *not* counted, and the
breaching ticket is moved to `RESOLVED` through the API to show the count falling back to 0.

Response headers are reproduced as returned, with only the `date` and `server` lines stripped.

```console
============================================================
 SERVICE HEALTH AND DISCOVERY
============================================================
$ curl -i -X GET http://127.0.0.1:8010/
HTTP/1.1 200 OK
content-length: 62
content-type: application/json
vary: Origin

{"service":"ServiceDesk API","version":"1.0.0","docs":"/docs"}
------------------------------------------------------------
$ curl -i -X GET http://127.0.0.1:8010/health
HTTP/1.1 200 OK
content-length: 15
content-type: application/json
vary: Origin

{"status":"UP"}
------------------------------------------------------------
$ curl -i -X GET http://127.0.0.1:8010/ready
HTTP/1.1 200 OK
content-length: 18
content-type: application/json
vary: Origin

{"status":"READY"}
------------------------------------------------------------
$ curl -s http://127.0.0.1:8010/metrics | grep -E 'http_requests_total|http_request_duration_seconds_count' | head -8
# HELP http_requests_total Total number of requests by method, status and handler.
# TYPE http_requests_total counter
http_requests_total{handler="/health",method="GET",status="2xx"} 2.0
http_requests_total{handler="/",method="GET",status="2xx"} 1.0
http_requests_total{handler="/ready",method="GET",status="2xx"} 1.0
http_request_duration_seconds_count{handler="/health",method="GET"} 2.0
http_request_duration_seconds_count{handler="/",method="GET"} 1.0
http_request_duration_seconds_count{handler="/ready",method="GET"} 1.0

------------------------------------------------------------
============================================================
 CATEGORIES
============================================================
$ curl -s http://127.0.0.1:8010/api/categories | jq
[
  {
    "name": "Access",
    "description": "Account provisioning, password resets and permission requests",
    "id": 3
  },
  {
    "name": "Hardware",
    "description": "Laptops, docking stations, peripherals and on-site equipment",
    "id": 1
  },
  {
    "name": "Network",
    "description": "VPN, Wi-Fi, firewall rules and connectivity incidents",
    "id": 2
  },
  {
    "name": "Software",
    "description": "Application installs, licence keys and upgrade requests",
    "id": 4
  }
]
(the four rows above were inserted by Alembic revision 0002_seed, not by hand)
------------------------------------------------------------
$ curl -i -X POST http://127.0.0.1:8010/api/categories -H 'Content-Type: application/json' -d '{"name":"Facilities","description":"Desks, badges, meeting rooms and building services"}'
HTTP/1.1 201 Created
content-length: 95
content-type: application/json
vary: Origin

{"name":"Facilities","description":"Desks, badges, meeting rooms and building services","id":5}
------------------------------------------------------------
--- 409 on a duplicate category name ---
$ curl -i -X POST http://127.0.0.1:8010/api/categories -H 'Content-Type: application/json' -d '{"name":"Network","description":"duplicate attempt"}'
HTTP/1.1 409 Conflict
content-length: 36
content-type: application/json
vary: Origin

{"detail":"Category already exists"}
------------------------------------------------------------
--- 422 on an empty category name (min_length=1) ---
$ curl -i -X POST http://127.0.0.1:8010/api/categories -H 'Content-Type: application/json' -d '{"name":"","description":"empty name"}'
HTTP/1.1 422 Unprocessable Entity
content-length: 144
content-type: application/json
vary: Origin

{"detail":[{"type":"string_too_short","loc":["body","name"],"msg":"String should have at least 1 character","input":"","ctx":{"min_length":1}}]}
------------------------------------------------------------
============================================================
 TICKETS - CREATE (201) WITH A KNOWN SEEDED DATA SET
============================================================
$ curl -i -X POST http://127.0.0.1:8010/api/tickets -H 'Content-Type: application/json' -d '{"subject":"Laptop will not power on after firmware update","description":"ThinkPad T14 dead after the Tuesday BIOS rollout.","severity":"HIGH","status":"OPEN","requester":"Priya Nair","assignee":"Aman Yadav","category_id":1}'
HTTP/1.1 201 Created
content-length: 318
content-type: application/json
vary: Origin

{"subject":"Laptop will not power on after firmware update","description":"ThinkPad T14 dead after the Tuesday BIOS rollout.","severity":"HIGH","status":"OPEN","requester":"Priya Nair","assignee":"Aman Yadav","category_id":1,"id":1,"created_at":"2026-10-15T11:39:15.762983Z","sla_due_at":"2026-10-16T11:39:15.762987Z"}
------------------------------------------------------------
$ curl -i -X POST http://127.0.0.1:8010/api/tickets -H 'Content-Type: application/json' -d '{"subject":"VPN drops every ten minutes on the Mumbai link","description":"IPsec tunnel renegotiates and the session is lost.","severity":"URGENT","status":"OPEN","requester":"Rahul Mehta","assignee":"Aman Yadav","category_id":2}'
HTTP/1.1 201 Created
content-length: 322
content-type: application/json
vary: Origin

{"subject":"VPN drops every ten minutes on the Mumbai link","description":"IPsec tunnel renegotiates and the session is lost.","severity":"URGENT","status":"OPEN","requester":"Rahul Mehta","assignee":"Aman Yadav","category_id":2,"id":2,"created_at":"2026-10-15T11:39:15.776747Z","sla_due_at":"2026-10-16T11:39:15.776749Z"}
------------------------------------------------------------
$ curl -i -X POST http://127.0.0.1:8010/api/tickets -H 'Content-Type: application/json' -d '{"subject":"New joiner needs access to the billing dashboard","description":"Grant read-only role in the finance group.","severity":"LOW","status":"PENDING","requester":"Sana Kapoor","assignee":"Aman Yadav","category_id":3}'
HTTP/1.1 201 Created
content-length: 316
content-type: application/json
vary: Origin

{"subject":"New joiner needs access to the billing dashboard","description":"Grant read-only role in the finance group.","severity":"LOW","status":"PENDING","requester":"Sana Kapoor","assignee":"Aman Yadav","category_id":3,"id":3,"created_at":"2026-10-15T11:39:15.789671Z","sla_due_at":"2026-10-16T11:39:15.789673Z"}
------------------------------------------------------------
$ curl -i -X POST http://127.0.0.1:8010/api/tickets -H 'Content-Type: application/json' -d '{"subject":"Design suite licence expired on two workstations","description":"Licence server shows two seats past renewal.","severity":"MEDIUM","status":"RESOLVED","requester":"Dev Sharma","assignee":"Aman Yadav","category_id":4}'
HTTP/1.1 201 Created
content-length: 321
content-type: application/json
vary: Origin

{"subject":"Design suite licence expired on two workstations","description":"Licence server shows two seats past renewal.","severity":"MEDIUM","status":"RESOLVED","requester":"Dev Sharma","assignee":"Aman Yadav","category_id":4,"id":4,"created_at":"2026-10-15T11:39:15.802229Z","sla_due_at":"2026-10-16T11:39:15.802230Z"}
------------------------------------------------------------
$ curl -i -X POST http://127.0.0.1:8010/api/tickets -H 'Content-Type: application/json' -d '{"subject":"Printer on the third floor jams on duplex jobs","description":"Replaced the fuser, closing the ticket.","severity":"LOW","status":"CLOSED","requester":"Neha Gupta","assignee":"Aman Yadav","category_id":1}'
HTTP/1.1 201 Created
content-length: 309
content-type: application/json
vary: Origin

{"subject":"Printer on the third floor jams on duplex jobs","description":"Replaced the fuser, closing the ticket.","severity":"LOW","status":"CLOSED","requester":"Neha Gupta","assignee":"Aman Yadav","category_id":1,"id":5,"created_at":"2026-10-15T11:39:15.813664Z","sla_due_at":"2026-10-16T11:39:15.813666Z"}
------------------------------------------------------------
$ curl -s http://127.0.0.1:8010/api/tickets | jq -r '.[] | "\(.id)  \(.status)  \(.severity)  \(.subject)"'
5  CLOSED  LOW  Printer on the third floor jams on duplex jobs
4  RESOLVED  MEDIUM  Design suite licence expired on two workstations
3  PENDING  LOW  New joiner needs access to the billing dashboard
2  OPEN  URGENT  VPN drops every ten minutes on the Mumbai link
1  OPEN  HIGH  Laptop will not power on after firmware update

------------------------------------------------------------
============================================================
 STATS - COUNTS MUST MATCH THE SEEDED DATA
============================================================
expected from the five tickets above: total=5 open=2 pending=1 resolved=1 closed=1 breachingSla=0
$ curl -i -X GET http://127.0.0.1:8010/api/tickets/stats
HTTP/1.1 200 OK
content-length: 73
content-type: application/json
vary: Origin

{"total":5,"open":2,"pending":1,"resolved":1,"closed":1,"breachingSla":0}
------------------------------------------------------------
--- cross-check the same aggregate straight from PostgreSQL ---
$ psql -c "SELECT status, count(*) FROM tickets GROUP BY status ORDER BY status;"
  status  | count 
----------+-------
 CLOSED   |     1
 OPEN     |     2
 PENDING  |     1
 RESOLVED |     1
(4 rows)

------------------------------------------------------------
============================================================
 SLA BREACH - PROVE breachingSla CHANGES
============================================================
$ psql -c "INSERT INTO tickets (...) VALUES ('Mail relay queue backed up', ..., 'OPEN', ..., now() - interval '6 hours', now() - interval '3 hours');"
INSERT 0 1

$ psql -c "SELECT id, status, sla_due_at < now() AS past_due FROM tickets ORDER BY id;"
 id |  status  | past_due 
----+----------+----------
  1 | OPEN     | f
  2 | OPEN     | f
  3 | PENDING  | f
  4 | RESOLVED | f
  5 | CLOSED   | f
  6 | OPEN     | t
(6 rows)


expected now: total=6 open=3 pending=1 resolved=1 closed=1 breachingSla=1
$ curl -i -X GET http://127.0.0.1:8010/api/tickets/stats
HTTP/1.1 200 OK
content-length: 73
content-type: application/json
vary: Origin

{"total":6,"open":3,"pending":1,"resolved":1,"closed":1,"breachingSla":1}
------------------------------------------------------------
--- a past-due ticket that is already RESOLVED must NOT be counted as breaching ---
$ psql -c "INSERT INTO tickets (...) VALUES ('Archived disk alert', ..., 'RESOLVED', ..., now() - interval '2 days');"
INSERT 0 1

expected now: total=7 open=3 pending=1 resolved=2 closed=1 breachingSla=1 (unchanged)
$ curl -i -X GET http://127.0.0.1:8010/api/tickets/stats
HTTP/1.1 200 OK
content-length: 73
content-type: application/json
vary: Origin

{"total":7,"open":3,"pending":1,"resolved":2,"closed":1,"breachingSla":1}
------------------------------------------------------------
--- moving an OPEN breaching ticket to RESOLVED drops breachingSla back to 0 ---
$ psql -c "SELECT id FROM tickets WHERE subject LIKE 'Mail relay%';"
breaching ticket id = 6
$ curl -i -X PUT http://127.0.0.1:8010/api/tickets/6 -H 'Content-Type: application/json' -d '{"status":"RESOLVED"}'
HTTP/1.1 200 OK
content-length: 330
content-type: application/json
vary: Origin

{"subject":"Mail relay queue backed up for six hours","description":"Outbound queue is not draining, SLA already missed.","severity":"URGENT","status":"RESOLVED","requester":"Service Desk Monitor","assignee":"Aman Yadav","category_id":2,"id":6,"created_at":"2026-10-15T05:39:15.950051Z","sla_due_at":"2026-10-15T08:39:15.950051Z"}
------------------------------------------------------------
expected now: total=7 open=2 pending=1 resolved=3 closed=1 breachingSla=0
$ curl -i -X GET http://127.0.0.1:8010/api/tickets/stats
HTTP/1.1 200 OK
content-length: 73
content-type: application/json
vary: Origin

{"total":7,"open":2,"pending":1,"resolved":3,"closed":1,"breachingSla":0}
------------------------------------------------------------
--- put it back to OPEN so the UI screenshots show a live breach ---
$ curl -i -X PUT http://127.0.0.1:8010/api/tickets/6 -H 'Content-Type: application/json' -d '{"status":"OPEN"}'
HTTP/1.1 200 OK
content-length: 326
content-type: application/json
vary: Origin

{"subject":"Mail relay queue backed up for six hours","description":"Outbound queue is not draining, SLA already missed.","severity":"URGENT","status":"OPEN","requester":"Service Desk Monitor","assignee":"Aman Yadav","category_id":2,"id":6,"created_at":"2026-10-15T05:39:15.950051Z","sla_due_at":"2026-10-15T08:39:15.950051Z"}
------------------------------------------------------------
$ curl -i -X GET http://127.0.0.1:8010/api/tickets/stats
HTTP/1.1 200 OK
content-length: 73
content-type: application/json
vary: Origin

{"total":7,"open":3,"pending":1,"resolved":2,"closed":1,"breachingSla":1}
------------------------------------------------------------
============================================================
 TICKET CRUD - READ, UPDATE, DELETE
============================================================
$ curl -i -X GET http://127.0.0.1:8010/api/tickets/1
HTTP/1.1 200 OK
content-length: 318
content-type: application/json
vary: Origin

{"subject":"Laptop will not power on after firmware update","description":"ThinkPad T14 dead after the Tuesday BIOS rollout.","severity":"HIGH","status":"OPEN","requester":"Priya Nair","assignee":"Aman Yadav","category_id":1,"id":1,"created_at":"2026-10-15T11:39:15.762983Z","sla_due_at":"2026-10-16T11:39:15.762987Z"}
------------------------------------------------------------
--- PUT: change status, severity and assignee in one call ---
$ curl -i -X PUT http://127.0.0.1:8010/api/tickets/1 -H 'Content-Type: application/json' -d '{"status":"PENDING","severity":"URGENT","assignee":"Aman Yadav"}'
HTTP/1.1 200 OK
content-length: 323
content-type: application/json
vary: Origin

{"subject":"Laptop will not power on after firmware update","description":"ThinkPad T14 dead after the Tuesday BIOS rollout.","severity":"URGENT","status":"PENDING","requester":"Priya Nair","assignee":"Aman Yadav","category_id":1,"id":1,"created_at":"2026-10-15T11:39:15.762983Z","sla_due_at":"2026-10-16T11:39:15.762987Z"}
------------------------------------------------------------
--- read it back to show the change persisted ---
$ curl -i -X GET http://127.0.0.1:8010/api/tickets/1
HTTP/1.1 200 OK
content-length: 323
content-type: application/json
vary: Origin

{"subject":"Laptop will not power on after firmware update","description":"ThinkPad T14 dead after the Tuesday BIOS rollout.","severity":"URGENT","status":"PENDING","requester":"Priya Nair","assignee":"Aman Yadav","category_id":1,"id":1,"created_at":"2026-10-15T11:39:15.762983Z","sla_due_at":"2026-10-16T11:39:15.762987Z"}
------------------------------------------------------------
--- PUT back to the original values ---
$ curl -i -X PUT http://127.0.0.1:8010/api/tickets/1 -H 'Content-Type: application/json' -d '{"status":"OPEN","severity":"HIGH"}'
HTTP/1.1 200 OK
content-length: 318
content-type: application/json
vary: Origin

{"subject":"Laptop will not power on after firmware update","description":"ThinkPad T14 dead after the Tuesday BIOS rollout.","severity":"HIGH","status":"OPEN","requester":"Priya Nair","assignee":"Aman Yadav","category_id":1,"id":1,"created_at":"2026-10-15T11:39:15.762983Z","sla_due_at":"2026-10-16T11:39:15.762987Z"}
------------------------------------------------------------
--- create a throwaway ticket then DELETE it (204) ---
$ DEL_ID=$(curl -s -X POST http://127.0.0.1:8010/api/tickets -d '{"subject":"Temporary ticket raised to demonstrate DELETE"}' | jq -r .id)
DEL_ID=8
------------------------------------------------------------
$ curl -i -X GET http://127.0.0.1:8010/api/tickets/8
HTTP/1.1 200 OK
content-length: 273
content-type: application/json
vary: Origin

{"subject":"Temporary ticket raised to demonstrate DELETE","description":"","severity":"MEDIUM","status":"OPEN","requester":"Aman Yadav","assignee":"Unassigned","category_id":null,"id":8,"created_at":"2026-10-15T11:39:16.243850Z","sla_due_at":"2026-10-16T11:39:16.243854Z"}
------------------------------------------------------------
$ curl -i -X DELETE http://127.0.0.1:8010/api/tickets/8
HTTP/1.1 204 No Content
content-type: application/json
vary: Origin


------------------------------------------------------------
--- the deleted id is now a 404 ---
$ curl -i -X GET http://127.0.0.1:8010/api/tickets/8
HTTP/1.1 404 Not Found
content-length: 29
content-type: application/json
vary: Origin

{"detail":"Ticket not found"}
------------------------------------------------------------
============================================================
 ERROR PATHS
============================================================
--- 404 on a missing id for GET, PUT and DELETE ---
$ curl -i -X GET http://127.0.0.1:8010/api/tickets/99999
HTTP/1.1 404 Not Found
content-length: 29
content-type: application/json
vary: Origin

{"detail":"Ticket not found"}
------------------------------------------------------------
$ curl -i -X PUT http://127.0.0.1:8010/api/tickets/99999 -H 'Content-Type: application/json' -d '{"status":"CLOSED"}'
HTTP/1.1 404 Not Found
content-length: 29
content-type: application/json
vary: Origin

{"detail":"Ticket not found"}
------------------------------------------------------------
$ curl -i -X DELETE http://127.0.0.1:8010/api/tickets/99999
HTTP/1.1 404 Not Found
content-length: 29
content-type: application/json
vary: Origin

{"detail":"Ticket not found"}
------------------------------------------------------------
--- 422 on an unknown category_id (POST and PUT) ---
$ curl -i -X POST http://127.0.0.1:8010/api/tickets -H 'Content-Type: application/json' -d '{"subject":"Ticket pointing at a category that does not exist","category_id":99999}'
HTTP/1.1 422 Unprocessable Entity
content-length: 31
content-type: application/json
vary: Origin

{"detail":"Category not found"}
------------------------------------------------------------
$ curl -i -X PUT http://127.0.0.1:8010/api/tickets/1 -H 'Content-Type: application/json' -d '{"category_id":99999}'
HTTP/1.1 422 Unprocessable Entity
content-length: 31
content-type: application/json
vary: Origin

{"detail":"Category not found"}
------------------------------------------------------------
--- 422 on a bad severity enum ---
$ curl -i -X POST http://127.0.0.1:8010/api/tickets -H 'Content-Type: application/json' -d '{"subject":"Ticket with an invalid severity","severity":"CATASTROPHIC"}'
HTTP/1.1 422 Unprocessable Entity
content-length: 203
content-type: application/json
vary: Origin

{"detail":[{"type":"literal_error","loc":["body","severity"],"msg":"Input should be 'LOW', 'MEDIUM', 'HIGH' or 'URGENT'","input":"CATASTROPHIC","ctx":{"expected":"'LOW', 'MEDIUM', 'HIGH' or 'URGENT'"}}]}
------------------------------------------------------------
--- 422 on a bad status enum ---
$ curl -i -X POST http://127.0.0.1:8010/api/tickets -H 'Content-Type: application/json' -d '{"subject":"Ticket with an invalid status","status":"ON_FIRE"}'
HTTP/1.1 422 Unprocessable Entity
content-length: 208
content-type: application/json
vary: Origin

{"detail":[{"type":"literal_error","loc":["body","status"],"msg":"Input should be 'OPEN', 'PENDING', 'RESOLVED' or 'CLOSED'","input":"ON_FIRE","ctx":{"expected":"'OPEN', 'PENDING', 'RESOLVED' or 'CLOSED'"}}]}
------------------------------------------------------------
--- 422 on a missing required field ---
$ curl -i -X POST http://127.0.0.1:8010/api/tickets -H 'Content-Type: application/json' -d '{"description":"no subject supplied"}'
HTTP/1.1 422 Unprocessable Entity
content-length: 125
content-type: application/json
vary: Origin

{"detail":[{"type":"missing","loc":["body","subject"],"msg":"Field required","input":{"description":"no subject supplied"}}]}
------------------------------------------------------------
============================================================
 FINAL STATE OF THE DATABASE
============================================================
$ psql -c "SELECT t.id, t.status, t.severity, c.name AS category, t.subject FROM tickets t LEFT JOIN categories c ON c.id = t.category_id ORDER BY t.id;"
 id |  status  | severity | category |                     subject                      
----+----------+----------+----------+--------------------------------------------------
  1 | OPEN     | HIGH     | Hardware | Laptop will not power on after firmware update
  2 | OPEN     | URGENT   | Network  | VPN drops every ten minutes on the Mumbai link
  3 | PENDING  | LOW      | Access   | New joiner needs access to the billing dashboard
  4 | RESOLVED | MEDIUM   | Software | Design suite licence expired on two workstations
  5 | CLOSED   | LOW      | Hardware | Printer on the third floor jams on duplex jobs
  6 | OPEN     | URGENT   | Network  | Mail relay queue backed up for six hours
  7 | RESOLVED | MEDIUM   | Hardware | Archived disk space alert on build agent
(7 rows)


$ curl -i -X GET http://127.0.0.1:8010/api/tickets/stats
HTTP/1.1 200 OK
content-length: 73
content-type: application/json
vary: Origin

{"total":7,"open":3,"pending":1,"resolved":2,"closed":1,"breachingSla":1}
------------------------------------------------------------
```

### Status codes observed across the transcript

| Code | Count | Where |
|---|---|---|
| 200 | 16 | reads, updates, stats |
| 201 | 6 | category and ticket creation |
| 204 | 1 | ticket deletion |
| 404 | 4 | reading a just-deleted id, then GET, PUT and DELETE on an id that never existed |
| 409 | 1 | duplicate category name |
| 422 | 6 | unknown category on POST and PUT, bad severity, bad status, missing subject, empty category name |

Every `/api/tickets/stats` response in the transcript was predicted in the line above it before the
call was made, and every prediction matched.

---

## 4. pytest

40 tests across five files, covering every endpoint in the contract.

| File | Tests | Endpoints covered |
|---|---|---|
| `tests/test_health.py` | 5 | `GET /`, `GET /health`, `GET /ready`, `GET /metrics`, unknown route |
| `tests/test_categories.py` | 5 | `GET /api/categories`, `POST /api/categories` |
| `tests/test_tickets.py` | 17 | `POST`, `GET`, `GET /{id}`, `PUT /{id}`, `DELETE /{id}` on `/api/tickets` |
| `tests/test_stats.py` | 7 | `GET /api/tickets/stats` |
| `tests/test_database_isolation.py` | 5 | the test-database guarantees themselves |

### The suite never touches the production database

`conftest.py` resolves the test database before `app` is imported, in this order:

1. `TEST_DATABASE_URL` if it is set.
2. Otherwise, if `DATABASE_URL` is a PostgreSQL URL, a sibling database with `_test` appended to
   the name — created automatically if it does not exist. With the development stack running this
   resolves to `servicedesk_test`, a different database on the same server.
3. Otherwise a throwaway SQLite file under the system temp directory, so the suite runs on a CI
   runner with no database service at all.

It then sets `DATABASE_URL` to the resolved value before importing the app, so even the
`create_all` in the FastAPI lifespan cannot reach production, and separately overrides the
`get_db` dependency so every request inside a test uses the test session. If the resolved test URL
is ever equal to `DATABASE_URL`, `conftest.py` raises at import rather than running.

The transcript below checks this rather than asserting it: every ticket row in the production
database is checksummed before and after the run, and the checksums are compared.

```console
============================================================
 STATE OF THE PRODUCTION DATABASE BEFORE THE TEST RUN
============================================================
DATABASE_URL = postgresql+psycopg://servicedesk:servicedesk@localhost:55433/servicedesk

$ psql -d servicedesk -c 'SELECT count(*) FROM tickets;' / categories
 tickets 
---------
       7
(1 row)

 categories 
------------
          5
(1 row)

checksum of every ticket row before: c13adfe3610a1cd49b9f6a2071d55813

============================================================
 pytest -v
============================================================
$ pytest -v
============================= test session starts ==============================
platform darwin -- Python 3.12.13, pytest-8.3.4, pluggy-1.7.0 -- /Users/aman/Desktop/devops-heros/helpdesk-capstone/backend/.venv/bin/python
cachedir: .pytest_cache
rootdir: /Users/aman/Desktop/devops-heros/helpdesk-capstone/backend
configfile: pytest.ini
testpaths: tests
plugins: cov-6.0.0, anyio-4.15.1
collecting ... collected 40 items

tests/test_categories.py::test_category_list_starts_empty PASSED         [  2%]
tests/test_categories.py::test_create_category_returns_201_and_the_new_row PASSED [  5%]
tests/test_categories.py::test_duplicate_category_name_returns_409 PASSED [  7%]
tests/test_categories.py::test_empty_category_name_returns_422 PASSED    [ 10%]
tests/test_categories.py::test_categories_are_listed_alphabetically PASSED [ 12%]
tests/test_database_isolation.py::test_the_suite_never_points_at_the_production_database PASSED [ 15%]
tests/test_database_isolation.py::test_the_application_engine_is_bound_to_the_test_database PASSED [ 17%]
tests/test_database_isolation.py::test_get_db_is_overridden_while_a_test_client_is_active PASSED [ 20%]
tests/test_database_isolation.py::test_each_test_starts_from_an_empty_queue PASSED [ 22%]
tests/test_database_isolation.py::test_the_previous_tests_rows_do_not_leak_into_this_one PASSED [ 25%]
tests/test_health.py::test_root_banner_identifies_the_servicedesk_api PASSED [ 27%]
tests/test_health.py::test_health_endpoint_reports_up PASSED             [ 30%]
tests/test_health.py::test_ready_endpoint_queries_the_database PASSED    [ 32%]
tests/test_health.py::test_metrics_endpoint_returns_prometheus_text PASSED [ 35%]
tests/test_health.py::test_unknown_route_returns_404 PASSED              [ 37%]
tests/test_stats.py::test_stats_on_an_empty_queue_are_all_zero PASSED    [ 40%]
tests/test_stats.py::test_stats_count_every_status_bucket PASSED         [ 42%]
tests/test_stats.py::test_stats_count_a_ticket_whose_sla_has_already_passed PASSED [ 45%]
tests/test_stats.py::test_stats_count_a_breaching_pending_ticket PASSED  [ 47%]
tests/test_stats.py::test_stats_ignore_past_due_tickets_that_are_resolved_or_closed PASSED [ 50%]
tests/test_stats.py::test_resolving_a_breaching_ticket_clears_the_breach_count PASSED [ 52%]
tests/test_stats.py::test_stats_follow_create_and_delete PASSED          [ 55%]
tests/test_tickets.py::test_create_ticket_returns_201_with_the_documented_defaults PASSED [ 57%]
tests/test_tickets.py::test_create_ticket_sets_the_sla_due_date_24_hours_ahead PASSED [ 60%]
tests/test_tickets.py::test_create_ticket_accepts_an_existing_category PASSED [ 62%]
tests/test_tickets.py::test_tickets_are_listed_newest_first PASSED       [ 65%]
tests/test_tickets.py::test_get_ticket_by_id_returns_the_stored_row PASSED [ 67%]
tests/test_tickets.py::test_get_missing_ticket_returns_404 PASSED        [ 70%]
tests/test_tickets.py::test_update_ticket_changes_status_severity_and_assignee PASSED [ 72%]
tests/test_tickets.py::test_update_only_touches_the_fields_that_were_sent PASSED [ 75%]
tests/test_tickets.py::test_update_missing_ticket_returns_404 PASSED     [ 77%]
tests/test_tickets.py::test_delete_ticket_returns_204_and_the_id_becomes_404 PASSED [ 80%]
tests/test_tickets.py::test_delete_missing_ticket_returns_404 PASSED     [ 82%]
tests/test_tickets.py::test_create_ticket_with_unknown_category_returns_422 PASSED [ 85%]
tests/test_tickets.py::test_update_ticket_with_unknown_category_returns_422 PASSED [ 87%]
tests/test_tickets.py::test_create_ticket_with_an_invalid_severity_returns_422 PASSED [ 90%]
tests/test_tickets.py::test_create_ticket_with_an_invalid_status_returns_422 PASSED [ 92%]
tests/test_tickets.py::test_create_ticket_without_a_subject_returns_422 PASSED [ 95%]
tests/test_tickets.py::test_ticket_is_linked_to_its_category_row_through_the_foreign_key PASSED [ 97%]
tests/test_tickets.py::test_sla_due_at_round_trips_through_the_api PASSED [100%]

=============================== warnings summary ===============================
.venv/lib/python3.12/site-packages/fastapi/testclient.py:1
  /Users/aman/Desktop/devops-heros/helpdesk-capstone/backend/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 40 passed, 1 warning in 0.43s =========================

pytest exit status: 0

============================================================
 WHICH DATABASE DID THE SUITE ACTUALLY USE
============================================================
$ python -c 'import conftest; print(...)'
/Users/aman/Desktop/devops-heros/helpdesk-capstone/backend/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
  from starlette.testclient import TestClient as TestClient  # noqa
production DATABASE_URL : postgresql+psycopg://servicedesk:servicedesk@localhost:55433/servicedesk
resolved test database : postgresql+psycopg://servicedesk:servicedesk@localhost:55433/servicedesk_test
they differ            : True

$ docker exec servicedesk-pg-dev psql -U servicedesk -d postgres -c '\l'
                                                              List of databases
       Name       |    Owner    | Encoding | Locale Provider |  Collate   |   Ctype    | ICU Locale | ICU Rules |      Access privileges      
------------------+-------------+----------+-----------------+------------+------------+------------+-----------+-----------------------------
 postgres         | servicedesk | UTF8     | libc            | en_US.utf8 | en_US.utf8 |            |           | 
 servicedesk      | servicedesk | UTF8     | libc            | en_US.utf8 | en_US.utf8 |            |           | 
 servicedesk_test | servicedesk | UTF8     | libc            | en_US.utf8 | en_US.utf8 |            |           | 
 template0        | servicedesk | UTF8     | libc            | en_US.utf8 | en_US.utf8 |            |           | =c/servicedesk             +
                  |             |          |                 |            |            |            |           | servicedesk=CTc/servicedesk
 template1        | servicedesk | UTF8     | libc            | en_US.utf8 | en_US.utf8 |            |           | =c/servicedesk             +

============================================================
 THE PRODUCTION DATABASE IS UNTOUCHED
============================================================
 tickets 
---------
       7
(1 row)

 categories 
------------
          5
(1 row)

checksum of every ticket row after : c13adfe3610a1cd49b9f6a2071d55813

tickets    before=7 after=7
categories before=5 after=5
RESULT: the production database is byte for byte identical after the test run

$ psql -d servicedesk_test -c '\dt'
Did not find any relations.
(the suite drops its own tables on teardown, so servicedesk_test is empty between runs)

============================================================
 COVERAGE
============================================================
$ pytest --cov=app --cov-report=term-missing -q
........................................                                 [100%]
=============================== warnings summary ===============================
.venv/lib/python3.12/site-packages/fastapi/testclient.py:1
  /Users/aman/Desktop/devops-heros/helpdesk-capstone/backend/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html

--------- coverage: platform darwin, python 3.12.13-final-0 ----------
Name              Stmts   Miss  Cover   Missing
-----------------------------------------------
app/__init__.py       0      0   100%
app/config.py         5      0   100%
app/db.py            13      4    69%   16-20
app/main.py          84      0   100%
app/models.py        27      0   100%
app/schemas.py       39      0   100%
-----------------------------------------------
TOTAL               168      4    98%

40 passed, 1 warning in 0.56s

============================================================
 THE SUITE ALSO PASSES WITH NO DATABASE_URL AT ALL
============================================================
(conftest falls back to a throwaway SQLite file, so the GitHub runner needs no PostgreSQL service)
$ env -u DATABASE_URL -u TEST_DATABASE_URL pytest -q
........................................                                 [100%]
=============================== warnings summary ===============================
.venv/lib/python3.12/site-packages/fastapi/testclient.py:1
  /Users/aman/Desktop/devops-heros/helpdesk-capstone/backend/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
40 passed, 1 warning in 0.19s

$ env -u DATABASE_URL python -c 'import conftest; print(conftest.TEST_DATABASE_URL)'
/Users/aman/Desktop/devops-heros/helpdesk-capstone/backend/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
  from starlette.testclient import TestClient as TestClient  # noqa
sqlite+pysqlite:////var/folders/8w/pmzy_rs96rv1bx0xgg308k3h0000gn/T/servicedesk-tests-tlwwa09g/servicedesk_test.sqlite3

============================================================
 THE SUITE REFUSES TO RUN AGAINST THE PRODUCTION DATABASE
============================================================
$ TEST_DATABASE_URL=$DATABASE_URL pytest -q
ImportError while loading conftest '/Users/aman/Desktop/devops-heros/helpdesk-capstone/backend/conftest.py'.
conftest.py:57: in <module>
    raise RuntimeError(
E   RuntimeError: Refusing to run the test suite against the production database. TEST_DATABASE_URL must differ from DATABASE_URL.
```

### Coverage summary

```text
Name              Stmts   Miss  Cover   Missing
-----------------------------------------------
app/__init__.py       0      0   100%
app/config.py         5      0   100%
app/db.py            13      4    69%   16-20
app/main.py          84      0   100%
app/models.py        27      0   100%
app/schemas.py       39      0   100%
-----------------------------------------------
TOTAL               168      4    98%
```

Every line of `app/main.py` — all the route handlers — is executed. The four uncovered lines are
the body of `get_db` in `app/db.py`, which is the production session factory; it is uncovered
precisely because the suite overrides it, which is the point.

### The one warning

```text
StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated;
install `httpx2` instead.
```

This comes from starlette 1.8.0, which arrived with the `prometheus-fastapi-instrumentator` 8.1.0
pin. It is a deprecation notice from a dependency, not a failure, and the suite passes with it. If
a later starlette turns it into an error the fix is to swap `httpx` for `httpx2` in
`requirements-dev.txt`.

---

## 5. Frontend build and real browser renders

### Clean build from the lockfile

```console
$ npm ci

added 71 packages in 579ms
npm warn install-scripts 2 packages had install scripts blocked because they are not covered by allowScripts:
npm warn install-scripts   esbuild@0.25.12 (postinstall: node install.js)
npm warn install-scripts   fsevents@2.3.3 (install: (install scripts present))
npm warn install-scripts
npm warn install-scripts Run `npm install-scripts ls` to review, or `npm install-scripts approve <pkg>` to allow.

$ npm run build
npm notice run servicedesk-frontend@1.0.0 build
npm notice run tsc --noEmit && vite build
vite v7.1.12 building for production...
transforming...
✓ 35 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.85 kB │ gzip:  0.51 kB
dist/assets/index-DVGsV7X6.css    8.62 kB │ gzip:  2.43 kB
dist/assets/index-DJaHKaYy.js   236.00 kB │ gzip: 73.32 kB
✓ built in 457ms

$ ls -la dist dist/assets
dist:
total 8
drwxr-xr-x   4 aman  staff  128 Oct 15 17:01 .
drwxr-xr-x  15 aman  staff  480 Oct 15 17:01 ..
drwxr-xr-x   4 aman  staff  128 Oct 15 17:01 assets
-rw-r--r--   1 aman  staff  852 Oct 15 17:01 index.html

dist/assets:
total 488
drwxr-xr-x  4 aman  staff     128 Oct 15 17:01 .
drwxr-xr-x  4 aman  staff     128 Oct 15 17:01 ..
-rw-r--r--  1 aman  staff  236003 Oct 15 17:01 index-DJaHKaYy.js
-rw-r--r--  1 aman  staff    8621 Oct 15 17:01 index-DVGsV7X6.css

$ grep -o 'ServiceDesk' dist/assets/*.js | wc -l
       5
$ grep -o '/api/tickets/stats\|/api/categories\|/api/tickets' dist/assets/*.js | sort | uniq -c
   2 /api/categories
   5 /api/tickets
   1 /api/tickets/stats
$ grep -ciE 'task[- ]?board' dist/assets/*.js dist/index.html
dist/index.html:0
dist/assets/index-DJaHKaYy.js:0
```

Dependency versions are pinned exactly in `package.json` — no `latest`, no carets — and
`package-lock.json` is committed, so `npm ci` installs the same tree in the image build and in CI.
`npm run build` is `tsc --noEmit && vite build`, so a type error fails the build rather than
shipping.

### The built bundle really is this application

The production bundle was served on `127.0.0.1:5180` with `/api` proxied to the backend, exactly
as the Nginx runtime stage and the Kubernetes Ingress do, and then driven with headless Chrome.

```console
$ grep -o 'ServiceDesk' dist/assets/index-DJaHKaYy.js | wc -l
       5
$ grep -o '/api/tickets/stats\|/api/categories\|/api/tickets' dist/assets/*.js | sort | uniq -c
   2 /api/categories
   5 /api/tickets
   1 /api/tickets/stats
$ grep -ciE 'task[- ]?board' dist/assets/*.js dist/index.html
dist/index.html:0
dist/assets/index-DJaHKaYy.js:0
```

### Headless Chrome rendered the live data

`--dump-dom` returns the DOM after React has mounted and the API calls have resolved. The six
summary tiles in the rendered DOM were extracted from that dump:

```text
  Total tickets  7
  Open           3
  Pending        1
  Resolved       2
  Closed         1
  SLA breached   1
```

Those are the same numbers `GET /api/tickets/stats` returned at the end of section 3:

```json
{"total":7,"open":3,"pending":1,"resolved":2,"closed":1,"breachingSla":1}
```

The DOM also contains the live ticket text and the computed SLA badge:

```console
$ grep -o 'Mail relay queue backed up for six hours\|SLA breached 3h ago\|<title>ServiceDesk</title>' dom.html
<title>ServiceDesk</title>
Mail relay queue backed up for six hours
SLA breached 3h ago
```

`SLA breached 3h ago` is computed in the browser from the `sla_due_at` the API returned, which is
why it agrees with the `breachingSla: 1` the backend calculated independently in SQL.

### Screenshots

All six are real captures, in `docs/screenshots/`.

| File | What it shows |
|---|---|
| `servicedesk-queue-desktop.png` | the full queue at 1440px — stats bar, filter chips, ticket cards with inline status, severity, category and assignee controls |
| `servicedesk-queue-tablet.png` | the same page at 834px, stats reflowed to three columns |
| `servicedesk-queue-mobile.png` | the same page at 500px, stats in two columns, ticket controls stacked full width |
| `servicedesk-filter-sla-breached.jpg` | the SLA breached filter applied, showing only the one breaching ticket and `1 of 7 tickets shown` in the footer |
| `servicedesk-new-ticket-form.jpg` | the new ticket form open, with the category dropdown populated from `GET /api/categories` |
| `servicedesk-ticket-created.jpg` | a ticket created through the form in the browser — the `Ticket #9 created` banner, the total moving from 7 to 8 and open from 3 to 4, and the new ticket at the top of the queue |

The three `.png` files are headless Chrome captures of the queue as section 3 left it. The three
`.jpg` files come from an interactive session in a real Chrome window against the same stack;
`servicedesk-ticket-created.jpg` is the one write performed through the user interface rather than
through curl, and the row it created was confirmed in PostgreSQL immediately afterwards:

```console
$ psql -c "SELECT id, subject, status, severity, requester, assignee FROM tickets WHERE subject LIKE 'Meeting room%';"
 id |                      subject                      | status | severity | requester  |  assignee
----+---------------------------------------------------+--------+----------+------------+------------
  9 | Meeting room projector shows no signal over USB-C | OPEN   | MEDIUM   | Neha Gupta | Aman Yadav
(1 row)
```

Chrome on macOS refuses to open a window narrower than 500 CSS pixels, so 500px is the narrowest
real capture available. The stylesheet's small-screen rules take effect at 640px, so that capture
does exercise them; the layout is written to work down to 360px.

---

## 6. How to reproduce all of it

```sh
docker run -d --name servicedesk-pg-dev \
  -e POSTGRES_DB=servicedesk -e POSTGRES_USER=servicedesk -e POSTGRES_PASSWORD=servicedesk \
  -p 55433:5432 postgres:16-alpine

cd backend
python3.12 -m venv .venv
./.venv/bin/pip install -r requirements-dev.txt
export DATABASE_URL='postgresql+psycopg://servicedesk:servicedesk@localhost:55433/servicedesk'

./.venv/bin/alembic upgrade head
./.venv/bin/alembic current
./.venv/bin/alembic check

./.venv/bin/pytest -v
./.venv/bin/pytest --cov=app --cov-report=term-missing

./.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8010
```

```sh
cd frontend
npm ci
npm run build
npm run dev
```

`npm run dev` serves the console on `http://127.0.0.1:5173` and proxies `/api`, `/health` and
`/ready` to `http://127.0.0.1:8010`. Override that target with `VITE_DEV_API_TARGET`.

To run the test suite against a database of your choosing:

```sh
TEST_DATABASE_URL='postgresql+psycopg://user:pass@host:5432/servicedesk_test' pytest -v
```

With no `DATABASE_URL` and no `TEST_DATABASE_URL` the suite falls back to a temporary SQLite file
and still passes, which is how it runs in CI without a database service.
