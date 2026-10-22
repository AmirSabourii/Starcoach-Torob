# Torob in-person shopping assistant: final report (2026-10-22)

## Agent accuracy, 60 questions (gpt-6-luna, reasoning_effort=none, max 4 tool rounds, max_completion_tokens=600)
| category | run1 (orig scorer) | run1 (fixed scorer) | run2 (lexical) | run3 (+recall layer, full) | run3 + 4 targeted re-runs |
|---|---|---|---|---|---|
| simple_lookup (7) | 6 | 6 | 7 | 7 | 7 |
| filtered_search (7) | 6 | 7 | 7 | 7 | 7 |
| nearest_stores (7) | 3 | 6 | 6 | 7 | 7 |
| cheapest_compare_stores (7) | 6 | 6 | 7 | 5 | 7 |
| compare_products (5) | 4 | 5 | 5 | 4 | 5 |
| freshness (4) | 4 | 4 | 4 | 4 | 4 |
| payment_installment (5) | 5 | 5 | 5 | 5 | 5 |
| store_contact (4) | 4 | 4 | 4 | 4 | 4 |
| unanswerable (8) | 8 | 8 | 8 | 8 | 8 |
| ambiguous (6) | 5 | 6 | 6 | 5 (6 rescored) | 6 |
| **overall** | **85.0%** | **95.0%** | **98.3%** | **93.3% (95.0% rescored)** | **100%*** |

\* "run3 + 4 targeted re-runs" swaps in K02, K07, C04 and A03 from small `--only` re-runs made after fixing the run3 regressions. It is **not** a clean full run: the other 56 items were not re-run with the final prompt. The cleanest full-run figures are run2 at 98.3% and run3 at 93.3% (95% rescored).

## Recall (recall_tests.json, 12 badly-written queries) — see recall_results.json
| mode | hit@5 | hit@10 | recall@5 | recall@10 |
|---|---|---|---|---|
| baseline lexical (before) | 0.50 | 0.58 | 0.48 | 0.53 |
| + alias/fuzzy/digit/ZWNJ | 1.00 | 1.00 | 0.88 | 0.89 |
| + LLM query expansion | 1.00 | 1.00 | 0.93 | 0.94 |
| + embeddings (text-embedding-3-small) | 1.00 | 1.00 | 0.93 | 0.94 |
| full (+ match grader) (after) | 1.00 | 1.00 | 0.97 | 0.98 |
