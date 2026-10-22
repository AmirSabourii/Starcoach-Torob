# Discovery / browsing tests (15)

baseline (7 tools, d1): 11/15 · final (with browse_catalog + installment/area store browse): 15/15

| id | kind | question | baseline | final | reason (final) |
|---|---|---|---|---|---|
| D01 | vague | یه کادو زیر ۵ میلیون برای یه نفر که عاشق گیمه چی بخرم؟ | PASS | PASS (d1) | options=4, prices=4, over_budget=[], clarify=False |
| D02 | vague | نمی‌دونم چی می‌خوام، یه چیز جالب تکنولوژی نشونم بده | PASS | PASS (d1) | options=0, prices=0, over_budget=[], clarify=True |
| D03 | budget | یه هندزفری خوب می‌خوام بودجه‌ام ۳ میلیونه | PASS | PASS (d1) | options=4, prices=4, over_budget=[], clarify=False |
| D04 | category_browse | چه برندهایی لپتاپ دارید؟ | FAIL | PASS (d2) | brands named=8 ['لنوو', 'ایسوس', 'اچ\u200cپی', 'اپل', 'دل', 'ایسر'], absent brands claimed=[] |
| D05 | category_browse | تو دسته‌ی کنسول بازی چیا هست؟ | PASS | PASS (d1) | console families=4, prices=11 |
| D06 | category_browse | ارزون‌ترین تلویزیون‌هاتون؟ | PASS | PASS (d2) | cheapest-3 present=['تلویزیون صنام مدل SLE-24M116 س', 'تلویزیون دنای مدل MC-32B3 سایز', 'تلویزیون سام الکترونیک مدل 32F'] |
| D07 | budget | با ۲۰ میلیون چه گوشی‌هایی می‌تونم بخرم؟ | PASS | PASS (d5) | options=5, prices=5, over_budget=[], clarify=False |
| D08 | store_browse | نزدیک میدان فردوسی چه فروشگاه‌هایی هست؟ | PASS | PASS (d1) | shops named: 5 correct, 0 outside GT, clarify=False |
| D09 | store_browse | کدوم فروشگاه‌ها پرداخت قسطی دارن؟ | FAIL | PASS (d2) | providers mentioned=4; shops named: 5 correct, 0 outside GT, clarify=False |
| D10 | similar_cheaper | چیزی شبیه ایرپاد ولی ارزون‌تر؟ | PASS | PASS (d3) | products=5, prices cheaper than AirPods (10,790,000)=5, clarify=False |
| D11 | budget | یه ساعت هوشمند خوب تا ۱۰ میلیون معرفی کن | PASS | PASS (d1) | options=3, prices=3, over_budget=[], clarify=False |
| D12 | vague | یه اسپیکر بلوتوثی برای مهمونی می‌خوام | FAIL | PASS (d2) | options=5, prices=5, over_budget=[], clarify=False |
| D13 | category_browse | گوشی سامسونگ ارزون چی دارید؟ | FAIL | PASS (d3) | cheapest-3 present=['گوشی سامسونگ (چین) A07 4G | حا', 'گوشی سامسونگ (ویتنام) A06 | حا'] |
| D14 | store_browse | کدوم فروشگاه‌های شیخ هادی کنسول بازی دارن؟ | PASS | PASS (d1) | shops named: 3 correct, 0 outside GT, clarify=False |
| D15 | vague | یه چیزی برای خونه می‌خوام | PASS | PASS (d1) | options=0, prices=0, over_budget=[], clarify=True |
