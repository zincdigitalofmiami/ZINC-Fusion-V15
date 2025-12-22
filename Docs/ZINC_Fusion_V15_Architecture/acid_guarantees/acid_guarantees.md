# ACID Guarantees

ACID stands for **Atomicity**, **Consistency**, **Isolation** and **Durability**.  The medallion architecture of the ZINC Fusion platform ensures these properties as data moves through the Bronze, Silver and Gold layers.  Databricks notes that the medallion pattern “guarantees atomicity, consistency, isolation, and durability as data passes through multiple layers of validations and transformations before being stored”【872581463529754†L37-L46】.

* **Atomicity** ensures that each pipeline transaction either commits completely or has no effect.  If a task fails, Dagster rolls back partial writes and retries the operation so that downstream data is never left half‑updated.
* **Consistency** enforces valid schemas and business constraints.  Silver‑layer jobs apply type casting and validation rules to ensure that records conform to expected formats and values.
* **Isolation** means concurrent jobs do not interfere with one another.  Delta Lake’s snapshot isolation allows multiple readers and writers to operate on the same table without corrupting data.
* **Durability** assures that committed data persists even in the face of failures.  ZINC Fusion leverages object‑storage versioning and transaction logs so that once data is written it cannot be lost or corrupted.

Dagster’s built‑in retry logic preserves atomicity by rerunning failed tasks without corrupting upstream data.  Combined with Delta‑Lake transaction logs, the platform provides ACID semantics across the lake‑house.
