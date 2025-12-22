# References

- **Databricks Documentation** – The medallion architecture documentation explains that the pattern organizes data into progressively higher‑quality layers and guarantees ACID properties during transformations【872581463529754†L37-L48】.  It also provides examples of bronze, silver and gold layers and their intended users【872581463529754†L48-L59】【872581463529754†L110-L119】.
- **Microsoft Fabric OneLake Guide** – The OneLake medallion architecture guide describes implementing bronze, silver and gold lakehouses and emphasises the importance of maintaining a raw source of truth for reprocessing【872581463529754†L123-L134】.  It highlights how medallion architectures help ensure atomicity, consistency, isolation and durability.
