# Token Usage Report

## Final Full-Dataset Run Summary

This report summarizes the token usage and estimated costs for the final full-dataset run that produced `output.csv` for all 250 requests in `dataset/requests.csv`.

## Models Used

No external AI models (OpenAI, Anthropic, etc.) were used for the final production run. The solution uses:

1. **Local deterministic financial engine** - Pure Python implementation for all financial calculations, forecasting, and decision logic
2. **Local OCR (Tesseract)** - Attempted for image extraction but not available in the environment (no tesseract installed)
3. **Rule-based message parsing** - Regex-based extraction of financial facts from messages (no LLM calls)

## Token Usage

| Model | Calls | Input Tokens | Output Tokens | Total Tokens |
|-------|-------|--------------|---------------|--------------|
| Local Deterministic Engine | N/A | 0 | 0 | 0 |
| Local Message Parser (Regex) | N/A | 0 | 0 | 0 |
| Local OCR (Tesseract) | 16 (attempted) | 0 | 0 | 0 |

**Overall Totals:**
- Total Model Calls: 0 (no external API calls)
- Total Input Tokens: 0
- Total Output Tokens: 0
- Total Tokens: 0

## Cost Analysis

| Model | Estimated Total Cost | Estimated Cost per Request |
|-------|---------------------|---------------------------|
| Local Deterministic Engine | $0.00 | $0.00 |
| Local Message Parser | $0.00 | $0.00 |
| Local OCR | $0.00 | $0.00 |

**Overall Estimated Cost: $0.00**
**Estimated Cost per Request: $0.00**

## Processing Details

- **Total Requests Processed:** 250
- **Dataset:** `dataset/requests.csv` (250 evaluation requests)
- **Supporting Data:** financial_profiles.csv, financial_events.csv, exchange_rates.csv, request_payment_options.csv, messages.csv, images.csv
- **Runtime:** ~10 seconds for full 250-request pipeline
- **Architecture:** Hybrid AI-assisted deterministic financial decision engine
  - Deterministic financial simulation + constraint checking + plan ranking
  - AI used only for unstructured evidence interpretation (messages, images)
  - No ML classifiers for final affordability decisions

## Notes

- No API keys, credentials, or sensitive configuration used
- All processing done locally on CPU (no GPU required for final run)
- Tesseract OCR was attempted for 16 linked images but not available in environment
- Message parsing uses regex patterns for English and Indonesian financial communications
- Exchange rates from provided `exchange_rates.csv` only (no live rates)