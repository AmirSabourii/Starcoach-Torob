# Torob dataset: findings for the eval

Source: `torob.sqlite`, built by `build_eval_db.py`. Queries were run on 2026-10-22. The newest price timestamp in the data is 2026-10-13 00:02 UTC.

## Size and cleaning
- 6,476 shops (3,792 have at least one offer), 225,903 products, 331,506 offers. Referential integrity is 100% (0 orphan offers).
- Prices: 314,634 valid. 1,789 dirty prices were set to NULL (1,645 below 1,000 and 144 above 1e11), and 15,083 were already missing, so 16,872 prices are NULL in total. 7,815 products have no valid price at all.
- Valid price quantiles (toman): p1 8,750 · p10 242k · median 3.7M · p90 49.9M · p99 420M.

## What is in the catalogue
- The long tail is electrical and industrial. Top categories by product count: building wire and cable (5,274), CCTV cameras (3,467), wristwatches (2,510), panel lights (2,370), phone cases (2,176), sockets and connectors, generators, pumps, relays, MCBs, inverters.
- Consumer electronics are also well covered: phones (814 products, 2,087 offers), laptops (505), TVs (358), smartwatches (462), consoles (PS5 / Xbox / Nintendo), speakers, headphones and AirPods. There is no food or grocery.
- Top brands: Samsung 3,351, Apple 2,719, Xiaomi 1,950, MVM 1,464, Dahua 1,072, Sony 752, HP 742, Canon 672, Hikvision 580, Hyundai 554. `brand_name` is NULL for 74% of products.
- Typical price bands, median offer (p10 to p90) in toman:
  - phones 70.8M (2.7M–360M)
  - laptops 302M (130M–598M)
  - TVs 162M (62M–490M)
  - PS5 consoles 188M (139M–363M)
  - AC units 136M (79M–223M)
  - speakers 27M
  - smartwatches 8.8M
  - CCTV cameras 7M
  - headphones 4.3M
  - building cable 1.1M

## Popular products ("compare stores" candidates)
- 190,649 products (84%) are sold in only 1 shop. 6,333 are sold in at least 5 shops, 1,240 in at least 10 and 133 in at least 20.
- The most widely carried products are:
  - Apple 20W 3-pin charger: 59 shops (the same title also has a second product_id in 29 shops).
  - Silex SG8 LITE / SG8-805S alarms: 51 / 49 shops.
  - 12V 30A switching PSU: 45 shops.
  - Harman Kardon Aura Studio 5: 37 shops.
  - Galaxy S25 FE 256/8: 34 shops.
  - JBL PartyBox Stage 320: 33 shops.
  - Galaxy A07, A17, A56 and A57: 23–28 shops each.
  - PS5 Slim (Digital and Standard): 24 shops each.
  - Redmi Note 15: 22 shops.
- Phones are dominated by Samsung A-series and S25/S26 and by Xiaomi Redmi/Poco. iPhone 16 and 17 are sold in 9–14 shops.

## Geography (all shops are in Tehran)
- Latitude 35.640–35.813 and longitude 51.305–51.509; no coordinates are missing.
- `location_label` has 30 values. Ferdowsi has 3,282 shops (1,962 with offers), Sheikh Hadi 1,587 (936) and Baharestan 616 (369). Together these three are about 85% of shops, all in the Jomhouri/Hafez/Ferdowsi electronics district.
- Smaller clusters: Aseman (Opal mall in Saadat Abad, 151), Bagh-e Feyz (107), Iranshahr (99), Sanaei (96), Sohrevardi (82), Tajrish (76) and Jannat Abad (68).
- Malls, matched by regex on the normalised address:
  - Alaeddin: about 563 matches across many spelling variants (علاالدین / علاءالدین / علالدین / "علاالدین ۲/۳"). Addresses like "روبروی/جنب علاءالدین" (opposite/next to Alaeddin) also match, so filter them out.
  - Boushehri: 357.
  - Ferdowsi World Trade Center (تجارت جهانی): 146.
  - Opal: 40.
  - Charsou: 30.
- What this means for "near me" questions: outside the centre the nearest carrier is often 6–12 km away. For example, the nearest S25 FE to Tajrish is about 8 km away, and the nearest Redmi Note 15 to Kianshahr about 6.2 km. A correct answer has to report these large distances honestly. Many shops in the same mall share nearly identical coordinates, so the eval allows 50 m distance ties.

## Data quirks the assistant must handle
- **Price outliers inside a product.** Of the 5,665 products priced in at least 5 shops, 516 have an offer below 0.4× the median and 813 have one above 2.5× the median. Examples:
  - PartyBox Stage 320 ranges from 87.8M to 860M.
  - PS5 Slim Digital goes up to 1.65B.
  - The 20W charger has a 480k offer against a median of about 3.5M, and that price was last changed in 2025-12.
  - The second AirPods Pro 3 listing has a 3.1M offer.
- **Stale prices.** 164,587 offers (50%) were updated within 30 days of 2026-10-22, and 5,702 are more than 1 year old. Some cheapest offers are very old, e.g. the Schneider LC1D09M7 offer at 500k was last changed 2023-05-11.
- **Duplicate titles.** 4,138 titles appear under more than one product_id (e.g. the 20W charger and AirPods Pro 3), so lookups should merge them.
- **Knock-offs and accessories.** 86 phones are "طرح" (lookalike knock-offs), e.g. "گوشی طرح اپل iphone 15 pro" at 18.9M. Searching "iPhone 15 Pro" mostly returns cases, LCDs and batteries. 57 phones are stock or used (استوک/کارکرده).
- **Inconsistent specs.** Two different spec schemas are in use (e.g. `تراشه` vs `مدل تراشه`, `ظرفیت رم` vs `رم اجرایی`), with mixed Persian and Latin digits. 81k products have no specs.
- **Payment and installments.**
  - Only 266 shops list `payment_options`: Torob Pay 190 (50 in-person), SnappPay 89, DigiPay 61, Tara 37 and Azki-loan 5. The channel is often `unknown`.
  - About 300 offer descriptions mention اقساط (installments). For example, only 1 of the 14 shops selling the iPhone 16 128GB Not-Active shows any installment evidence.
- **Shop info.** Phones are synthetic and written in Persian digits. 2,003 shops have empty `weekly_hours`. Only 112 shops have a website or Instagram.
- **Missing data.** There is no stock or quantity, no reviews, no price history (only the last change) and no cities other than Tehran. These are the basis for the negative tests.

## DB conveniences (torob.sqlite)
- Tables: `shops`, `products` and `offers`. Prices are cleaned in `price_toman`; `price_toman_raw` keeps the original and `price_status` records the cleaning outcome.
- Parsed side tables: `shop_categories`, `shop_payment_options`, `shop_hours` and `product_specs`.
- `product_stats` holds n_offers, n_shops, min/max price and the latest price change for each product.
- `products_fts` is an FTS5 index over normalised title, brand, model and category (ی/ک, digits and ZWNJ normalised). Normalise query strings the same way, e.g. `norm()` in build_eval_db.py.
- Indexes on product_id, shop_id, price, brand, category, location_label and lat/lon.
