# Schema and quality report: Google Analytics sample

Source wildcard: `bigquery-public-data.google_analytics_sample.ga_sessions_*`
Raw file glob: `data/raw/ga_sessions/*.parquet`

## Overall counts

- Raw session rows: **903,653**
- Distinct sessions `(fullVisitorId, visitId)`: **902,755**
- Duplicate session keys: **898**
- Date range: **20160801 -> 20170801**
- Sessions with `totals.transactions`: **11,552**
- Transaction-session rate: **1.2784%**
- Sum of `totals.transactionRevenue`: **1,540,071,240,000** micros

## Per-quarter counts

| Quarter | Rows | Distinct sessions | Transactions | First day | Last day |
|---|---:|---:|---:|---|---|
| 2016Q3 | 145,791 | 145,622 | 2,015 | 20160801 | 20160930 |
| 2016Q4 | 290,602 | 290,384 | 3,186 | 20161001 | 20161231 |
| 2017Q1 | 196,817 | 196,645 | 2,288 | 20170101 | 20170331 |
| 2017Q2 | 196,075 | 195,845 | 2,989 | 20170401 | 20170630 |
| 2017Q3 | 74,368 | 74,263 | 1,074 | 20170701 | 20170801 |

## Manifests

| Quarter | Manifest rows | Range start | Range end | Checksum |
|---|---:|---|---|---|
| 2016Q3 | 145791 | 20160801 | 20160930 | verified |
| 2016Q4 | 290602 | 20161001 | 20161231 | verified |
| 2017Q1 | 196817 | 20170101 | 20170331 | verified |
| 2017Q2 | 196075 | 20170401 | 20170630 | verified |
| 2017Q3 | 74368 | 20170701 | 20170801 | verified |

## Key-field null counts

| Field | Null rows |
|---|---:|
| `visitorId` | 903,653 |
| `visitNumber` | 0 |
| `visitId` | 0 |
| `visitStartTime` | 0 |
| `date` | 0 |
| `fullVisitorId` | 0 |
| `channelGrouping` | 0 |
| `socialEngagementType` | 0 |
| `totals` | 0 |
| `trafficSource` | 0 |
| `device` | 0 |
| `geoNetwork` | 0 |
| `hits` | 0 |
| `customDimensions` | 0 |

## Nested hit statistics

- Average hits per session: **4.60**
- Minimum hits per session: **1**
- Maximum hits per session: **500**

## Observed raw schema

| Column | Type |
|---|---|
| `visitorId` | `BIGINT` |
| `visitNumber` | `BIGINT` |
| `visitId` | `BIGINT` |
| `visitStartTime` | `BIGINT` |
| `date` | `VARCHAR` |
| `totals` | `STRUCT(visits BIGINT, hits BIGINT, pageviews BIGINT, timeOnSite BIGINT, bounces BIGINT, transactions BIGINT, transactionRevenue BIGINT, newVisits BIGINT, screenviews BIGINT, uniqueScreenviews BIGINT, timeOnScreen BIGINT, totalTransactionRevenue BIGINT, sessionQualityDim BIGINT)` |
| `trafficSource` | `STRUCT(referralPath VARCHAR, campaign VARCHAR, "source" VARCHAR, medium VARCHAR, keyword VARCHAR, adContent VARCHAR, adwordsClickInfo STRUCT(campaignId BIGINT, adGroupId BIGINT, creativeId BIGINT, criteriaId BIGINT, page BIGINT, slot VARCHAR, criteriaParameters VARCHAR, gclId VARCHAR, customerId BIGINT, adNetworkType VARCHAR, targetingCriteria STRUCT(boomUserlistId BIGINT), isVideoAd BOOLEAN), isTrueDirect BOOLEAN, campaignCode VARCHAR)` |
| `device` | `STRUCT(browser VARCHAR, browserVersion VARCHAR, browserSize VARCHAR, operatingSystem VARCHAR, operatingSystemVersion VARCHAR, isMobile BOOLEAN, mobileDeviceBranding VARCHAR, mobileDeviceModel VARCHAR, mobileInputSelector VARCHAR, mobileDeviceInfo VARCHAR, mobileDeviceMarketingName VARCHAR, flashVersion VARCHAR, javaEnabled BOOLEAN, "language" VARCHAR, screenColors VARCHAR, screenResolution VARCHAR, deviceCategory VARCHAR)` |
| `geoNetwork` | `STRUCT(continent VARCHAR, subContinent VARCHAR, country VARCHAR, region VARCHAR, metro VARCHAR, city VARCHAR, cityId VARCHAR, networkDomain VARCHAR, latitude VARCHAR, longitude VARCHAR, networkLocation VARCHAR)` |
| `customDimensions` | `STRUCT("index" BIGINT, "value" VARCHAR)[]` |
| `hits` | `STRUCT(hitNumber BIGINT, "time" BIGINT, "hour" BIGINT, "minute" BIGINT, isSecure BOOLEAN, isInteraction BOOLEAN, isEntrance BOOLEAN, isExit BOOLEAN, referer VARCHAR, page STRUCT(pagePath VARCHAR, hostname VARCHAR, pageTitle VARCHAR, searchKeyword VARCHAR, searchCategory VARCHAR, pagePathLevel1 VARCHAR, pagePathLevel2 VARCHAR, pagePathLevel3 VARCHAR, pagePathLevel4 VARCHAR), "transaction" STRUCT(transactionId VARCHAR, transactionRevenue BIGINT, transactionTax BIGINT, transactionShipping BIGINT, affiliation VARCHAR, currencyCode VARCHAR, localTransactionRevenue BIGINT, localTransactionTax BIGINT, localTransactionShipping BIGINT, transactionCoupon VARCHAR), item STRUCT(transactionId VARCHAR, productName VARCHAR, productCategory VARCHAR, productSku VARCHAR, itemQuantity BIGINT, itemRevenue BIGINT, currencyCode VARCHAR, localItemRevenue BIGINT), contentInfo STRUCT(contentDescription VARCHAR), appInfo STRUCT("name" VARCHAR, "version" VARCHAR, id VARCHAR, installerId VARCHAR, appInstallerId VARCHAR, appName VARCHAR, appVersion VARCHAR, appId VARCHAR, screenName VARCHAR, landingScreenName VARCHAR, exitScreenName VARCHAR, screenDepth VARCHAR), exceptionInfo STRUCT(description VARCHAR, isFatal BOOLEAN, exceptions BIGINT, fatalExceptions BIGINT), eventInfo STRUCT(eventCategory VARCHAR, eventAction VARCHAR, eventLabel VARCHAR, eventValue BIGINT), product STRUCT(productSKU VARCHAR, v2ProductName VARCHAR, v2ProductCategory VARCHAR, productVariant VARCHAR, productBrand VARCHAR, productRevenue BIGINT, localProductRevenue BIGINT, productPrice BIGINT, localProductPrice BIGINT, productQuantity BIGINT, productRefundAmount BIGINT, localProductRefundAmount BIGINT, isImpression BOOLEAN, isClick BOOLEAN, customDimensions STRUCT("index" BIGINT, "value" VARCHAR)[], customMetrics STRUCT("index" BIGINT, "value" BIGINT)[], productListName VARCHAR, productListPosition BIGINT, productCouponCode VARCHAR)[], promotion STRUCT(promoId VARCHAR, promoName VARCHAR, promoCreative VARCHAR, promoPosition VARCHAR)[], promotionActionInfo STRUCT(promoIsView BOOLEAN, promoIsClick BOOLEAN), refund STRUCT(refundAmount BIGINT, localRefundAmount BIGINT), eCommerceAction STRUCT(action_type VARCHAR, step BIGINT, "option" VARCHAR), experiment STRUCT(experimentId VARCHAR, experimentVariant VARCHAR)[], publisher STRUCT(dfpClicks BIGINT, dfpImpressions BIGINT, dfpMatchedQueries BIGINT, dfpMeasurableImpressions BIGINT, dfpQueries BIGINT, dfpRevenueCpm BIGINT, dfpRevenueCpc BIGINT, dfpViewableImpressions BIGINT, dfpPagesViewed BIGINT, adsenseBackfillDfpClicks BIGINT, adsenseBackfillDfpImpressions BIGINT, adsenseBackfillDfpMatchedQueries BIGINT, adsenseBackfillDfpMeasurableImpressions BIGINT, adsenseBackfillDfpQueries BIGINT, adsenseBackfillDfpRevenueCpm BIGINT, adsenseBackfillDfpRevenueCpc BIGINT, adsenseBackfillDfpViewableImpressions BIGINT, adsenseBackfillDfpPagesViewed BIGINT, adxBackfillDfpClicks BIGINT, adxBackfillDfpImpressions BIGINT, adxBackfillDfpMatchedQueries BIGINT, adxBackfillDfpMeasurableImpressions BIGINT, adxBackfillDfpQueries BIGINT, adxBackfillDfpRevenueCpm BIGINT, adxBackfillDfpRevenueCpc BIGINT, adxBackfillDfpViewableImpressions BIGINT, adxBackfillDfpPagesViewed BIGINT, adxClicks BIGINT, adxImpressions BIGINT, adxMatchedQueries BIGINT, adxMeasurableImpressions BIGINT, adxQueries BIGINT, adxRevenue BIGINT, adxViewableImpressions BIGINT, adxPagesViewed BIGINT, adsViewed BIGINT, adsUnitsViewed BIGINT, adsUnitsMatched BIGINT, viewableAdsViewed BIGINT, measurableAdsViewed BIGINT, adsPagesViewed BIGINT, adsClicked BIGINT, adsRevenue BIGINT, dfpAdGroup VARCHAR, dfpAdUnits VARCHAR, dfpNetworkId VARCHAR), customVariables STRUCT("index" BIGINT, customVarName VARCHAR, customVarValue VARCHAR)[], customDimensions STRUCT("index" BIGINT, "value" VARCHAR)[], customMetrics STRUCT("index" BIGINT, "value" BIGINT)[], "type" VARCHAR, social STRUCT(socialInteractionNetwork VARCHAR, socialInteractionAction VARCHAR, socialInteractions BIGINT, socialInteractionTarget VARCHAR, socialNetwork VARCHAR, uniqueSocialInteractions BIGINT, hasSocialSourceReferral VARCHAR, socialInteractionNetworkAction VARCHAR), latencyTracking STRUCT(pageLoadSample BIGINT, pageLoadTime BIGINT, pageDownloadTime BIGINT, redirectionTime BIGINT, speedMetricsSample BIGINT, domainLookupTime BIGINT, serverConnectionTime BIGINT, serverResponseTime BIGINT, domLatencyMetricsSample BIGINT, domInteractiveTime BIGINT, domContentLoadedTime BIGINT, userTimingValue BIGINT, userTimingSample BIGINT, userTimingVariable VARCHAR, userTimingCategory VARCHAR, userTimingLabel VARCHAR), sourcePropertyInfo STRUCT(sourcePropertyDisplayName VARCHAR, sourcePropertyTrackingId VARCHAR), contentGroup STRUCT(contentGroup1 VARCHAR, contentGroup2 VARCHAR, contentGroup3 VARCHAR, contentGroup4 VARCHAR, contentGroup5 VARCHAR, previousContentGroup1 VARCHAR, previousContentGroup2 VARCHAR, previousContentGroup3 VARCHAR, previousContentGroup4 VARCHAR, previousContentGroup5 VARCHAR, contentGroupUniqueViews1 BIGINT, contentGroupUniqueViews2 BIGINT, contentGroupUniqueViews3 BIGINT, contentGroupUniqueViews4 BIGINT, contentGroupUniqueViews5 BIGINT), dataSource VARCHAR, publisher_infos STRUCT(dfpClicks BIGINT, dfpImpressions BIGINT, dfpMatchedQueries BIGINT, dfpMeasurableImpressions BIGINT, dfpQueries BIGINT, dfpRevenueCpm BIGINT, dfpRevenueCpc BIGINT, dfpViewableImpressions BIGINT, dfpPagesViewed BIGINT, adsenseBackfillDfpClicks BIGINT, adsenseBackfillDfpImpressions BIGINT, adsenseBackfillDfpMatchedQueries BIGINT, adsenseBackfillDfpMeasurableImpressions BIGINT, adsenseBackfillDfpQueries BIGINT, adsenseBackfillDfpRevenueCpm BIGINT, adsenseBackfillDfpRevenueCpc BIGINT, adsenseBackfillDfpViewableImpressions BIGINT, adsenseBackfillDfpPagesViewed BIGINT, adxBackfillDfpClicks BIGINT, adxBackfillDfpImpressions BIGINT, adxBackfillDfpMatchedQueries BIGINT, adxBackfillDfpMeasurableImpressions BIGINT, adxBackfillDfpQueries BIGINT, adxBackfillDfpRevenueCpm BIGINT, adxBackfillDfpRevenueCpc BIGINT, adxBackfillDfpViewableImpressions BIGINT, adxBackfillDfpPagesViewed BIGINT, adxClicks BIGINT, adxImpressions BIGINT, adxMatchedQueries BIGINT, adxMeasurableImpressions BIGINT, adxQueries BIGINT, adxRevenue BIGINT, adxViewableImpressions BIGINT, adxPagesViewed BIGINT, adsViewed BIGINT, adsUnitsViewed BIGINT, adsUnitsMatched BIGINT, viewableAdsViewed BIGINT, measurableAdsViewed BIGINT, adsPagesViewed BIGINT, adsClicked BIGINT, adsRevenue BIGINT, dfpAdGroup VARCHAR, dfpAdUnits VARCHAR, dfpNetworkId VARCHAR)[])[]` |
| `fullVisitorId` | `VARCHAR` |
| `userId` | `VARCHAR` |
| `clientId` | `VARCHAR` |
| `channelGrouping` | `VARCHAR` |
| `socialEngagementType` | `VARCHAR` |

## Notes

- Raw files are treated as immutable source inputs.
- Nested BigQuery structures are preserved as DuckDB/Parquet-compatible structs and lists.
- `totals.transactions IS NOT NULL` is used as the session-level purchase-conversion proxy.
- `visitorId` is null in every observed raw row, so `fullVisitorId` and `visitId` are the usable session identity fields.
- Duplicate session keys are reported but not removed in the raw layer; cleaning/normalization belongs in the transformation layer.
