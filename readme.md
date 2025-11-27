# **IntegrateAI / QAGraph — Automated Test Generation Framework**

Writing integration tests often feels like going to the gym after a long day —
you *know* it’s good for you, but it’s also the first thing you postpone.

And digging through 50-page requirement docs to produce test cases?
Feels like scrolling Netflix looking for something interesting. 😅

But here’s the reality:

* Fixing a bug in production costs **30× more** than catching it in tests.
* Teams with poor test coverage see **2–3× more production incidents**.
* Around **70% of PagerDuty alerts** stem from missing integration tests.

**Tests aren’t paperwork. They’re the last safety net before “deploy.”**
IntegrateAI (powered by **QAGraph**) makes generating them dramatically easier, faster, and more reliable.

---

# 🚀 **What Is IntegrateAI / QAGraph?**

QAGraph is a **multi-stage, reflection-driven test generation pipeline** that turns:

* **Design Documents** → Test Scenarios + Test Cases (4-Node Flow)
* **Swagger/OpenAPI Specs** → Test Scenarios + Test Cases + Executable Test Code (2-Node Flow)

It’s like hiring a smart intern —
except this intern comes with a built-in mentor, reviews its own work, and never forgets anything.

---

# 🎯 **Why Not Just Use ChatGPT Once?**

Most single-shot LLM answers fail because design docs lack context.
QAGraph solves this using:

### **✔ Multi-Step Refinement (Assist → Reflect → Assist → Reflect)**

Each stage validates, improves, and filters outputs.

### **✔ Quality Gates**

Bad scenarios are rejected and regenerated.

### **✔ MemorySaver Checkpoints**

The system resumes from last good state → cheaper + stable.

---

# 🔍 **How QAGraph Works (User Journey)**

## **1. Upload Requirement Document / Swagger**

Developers or QA provide:

* FRD / Design Doc
* or swagger.json (API spec)

## **2. Stage 1 – Assist: AI Generates Test Scenarios**

The model drafts initial scenarios:

* Valid flows
* Error paths
* Edge cases

Example:
**Login API** → “correct password”, “wrong password”, “expired token”, …

## **3. Stage 1 – Reflect: AI Validates Scenarios**

It checks:

* Duplicates
* Missing coverage
* Logical gaps
* Conflicts with doc

Retries until scenarios reach quality threshold.

## **4. Stage 2 – Assist: Expand Into Full Test Cases**

Each scenario becomes a structured test case:

1. Steps
2. Expected results
3. Preconditions
4. Validation rules

## **5. Stage 2 – Reflect: Evaluate Test Strength**

The test cases are analyzed for:

* Coverage
* Clarity
* Flakiness
* Mutation-test strength

Weak tests → regenerated.

## **6. MemorySaver Keeps State**

If the process stops mid-way:

* No need to regenerate
* Resume from checkpoint

---

# 🏗 **Architectures**

## **Use Case 1 — Design Doc → Test Cases (4-Node Pipeline)**

<img width="912" height="1279" alt="image" src="https://github.com/user-attachments/assets/d8a47819-4d8b-44e5-af94-f3974a7b277a" />

Best for **document-heavy projects**.

**Nodes:**

1. Generate test scenarios
2. Evaluate scenarios
3. Quality Gate
4. Generate test cases
5. Evaluate test cases
6. Final Quality Gate

## **Use Case 2 — Swagger → Test Cases + Test Code (2-Node Pipeline)**

<img width="547" height="1600" alt="image" src="https://github.com/user-attachments/assets/b686c2d9-87ee-4779-9241-b6b834f23eb4" />
<img width="1600" height="900" alt="image" src="https://github.com/user-attachments/assets/e7a4d777-c2a8-4f1d-aa60-0bfb165837b4" />

Best for **API / integration testing**.

**Nodes:**

1. Generate test cases
2. Evaluate test cases

---

# 🧠 **Why 4 Nodes? (For Design Docs)**

<img width="1600" height="900" alt="image" src="https://github.com/user-attachments/assets/e6a18a9d-89fa-4232-b22c-e6389074a118" />

Design docs are vague → LLMs hallucinate.
A phased process:

* Extracts scenarios
* Validates them
* Expands
* Re-validates

This **iterative reflection** ensures precision.

---

# 📦 **After Clustering: Processing Pipeline**

Input files:

```
qagraph_input.json  → endpoint clusters
swagger.json        → full API specification
```

## **Step 1 — Orchestrator (`src/test_generator.py`)**

* Loads clusters + Swagger
* Creates OpenAI thread
* Feeds batches into QAGraph

## **Step 2 — Batch Processor (`src/qa_agent/test_cases_graph.py`)**

For each batch:

* Build prompt with endpoint metadata
* Fetch AI output (JSON)
* Parse → save test cases
* Capture JSON errors

**Output:**

* Executable test cases
* Recommended folder structure
* Logs

---

# 🧩 **Endpoint Clustering**

Clustering improves test quality and consistency.

### ✔ Better context

Endpoints in the same cluster share logic → more accurate tests.

### ✔ E2E flows

Allow **CRUD chains** (POST → GET → PUT → DELETE).

### ✔ Resuable setup/teardown

Factories shared across cluster.

---

# 🧪 **Clustering Algorithm**

## **1. Raw Data Extraction**

From Swagger JSON:

* Path
* Method
* Description
* Parameters

## **2. Initial Grouping**

* **By tag** (preferred)
* **By path prefix** (fallback)

## **3. Refinement**

Split by:

* Authentication
* Operation type:

  * POST = Create
  * GET = Read
  * PUT/PATCH = Update
  * DELETE = Delete

## **4. Agglomerative Hierarchical Clustering (AHC)**

Steps:

* Convert endpoint text → TF-IDF vectors
* Compute cosine similarity
* Apply AHC
* Limit cluster size (<10 endpoints)

**Result → clean, coherent endpoint clusters**

---
# 🔢 **How do you Evaluate**

<img width="1600" height="900" alt="image" src="https://github.com/user-attachments/assets/6b39d2aa-f091-4c4a-8ebd-392a60ceda60" />


# 🔢 **Reranking Framework (CI + NI)**

We prioritize scenarios using:

## **Correlation Index (CI)**

| Score | Meaning                    |
| ----- | -------------------------- |
| 1.0   | Explicit in design         |
| 0.75  | Strongly implied           |
| 0.5   | Logical but not referenced |
| 0.25  | Weak connection            |
| 0.0   | Not related                |

## **Necessity Index (NI)**

Base score from FRD/UX:

| Score | Meaning            |
| ----- | ------------------ |
| 1.0   | Must-have          |
| 0.75  | Strongly implied   |
| 0.5   | Stability fallback |
| 0.25  | Nice-to-have       |
| 0.0   | Unnecessary        |

### **Test-Type Multiplier**

* UI test for UI → ×1.0
* Backend test for backend → ×1.0
* Type mismatch → ×0.5

**Final NI = Base × Multiplier**

## **Final Rank Score**

```
Rank = (0.5 × CI) + (0.5 × NI)
```

---

# ✅ **Final Output**

You receive:

* Clean test scenarios
* High-quality test cases
* Executable test code (Swagger flow)
* Logical folder structure
* Full audit trail
* No duplicates, no hallucinations

---

# 🧵 **One-Liner Summary**

**“QAGraph acts like a smart intern with a built-in mentor — generating tests, evaluating them, fixing mistakes, and remembering progress.”**

---
