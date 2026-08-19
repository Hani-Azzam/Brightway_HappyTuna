# Persona Attributes

## 1. Customer Agent Attributes

| Attribute          | Type  | Range     | Meaning                                                                 |
| ------------------ | ----- | --------- | ----------------------------------------------------------------------- |
| loyalty            | float | 0.0 - 1.0 | How loyal the customer is to HappyTuna before the crisis                |
| trust_level        | float | 0.0 - 1.0 | Current trust in the company                                            |
| risk_sensitivity   | float | 0.0 - 1.0 | How worried the customer is about food safety                           |
| price_sensitivity  | float | 0.0 - 1.0 | How much price affects the buying decision                              |
| complaint_tendency | float | 0.0 - 1.0 | How likely the customer is to complain or open a support ticket         |
| forgiveness_level  | float | 0.0 - 1.0 | How likely the customer is to forgive the company after a good response |

## Customer Possible Actions

* buy_product
* stop_buying
* return_product
* open_support_ticket
* complain_on_social_media
* recommend_company
* wait_for_more_information

---

## 2. Influencer Agent Attributes

| Attribute           | Type    | Range     | Meaning                                                               |
| ------------------- | ------- | --------- | --------------------------------------------------------------------- |
| audience_size       | integer | 1,000+    | Number of followers                                                   |
| influence_level     | float   | 0.0 - 1.0 | How strongly the influencer can affect public opinion                 |
| credibility         | float   | 0.0 - 1.0 | How much the audience trusts this influencer                          |
| sensationalism      | float   | 0.0 - 1.0 | How dramatic or emotional the influencer’s content is                 |
| controversy_seeking | float   | 0.0 - 1.0 | How likely the influencer is to create conflict or attack the company |
| brand_support       | float   | 0.0 - 1.0 | How positive the influencer is toward HappyTuna before the crisis     |
| viral_probability   | float   | 0.0 - 1.0 | Chance that the influencer’s post becomes viral                       |

## Influencer Possible Actions

* post_content
* share_news
* criticize_company
* support_company
* push_narrative
* start_campaign
* wait_before_posting
