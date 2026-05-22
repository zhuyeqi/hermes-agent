"""ERM travel reimbursement display-name → PK maps (single source for preflight + save)."""

from __future__ import annotations

VEHICLE_TO_PK: dict[str, str] = {
    "飞机（商务舱）": "1001C110000000006HLL",
    "飞机（经济舱）": "1001C110000000006HLN",
    "火车（商务座）": "1001A110000000002YRS",
    "火车（一等座）": "1001C110000000006HLO",
    "火车（二等座）": "1001A110000000002YRU",
    "出租车": "1001C110000000006HLP",
    "公交/地铁": "1001C110000000006HLQ",
    "长途巴士": "1001A110000000002YRX",
    "轮船": "1001A110000000002YRY",
    "其他": "1001A110000000002YS1",
}

INVOICE_FORM_TO_PK: dict[str, str] = {
    "飞机行程单": "1001W210000000022G8D",
    "火车电子报销凭证": "1001W210000000022G8E",
    "火车纸质报销凭证": "1001W210000000022G8F",
    "长途巴士、轮船、出租车报销凭证": "1001W210000000022G9C",
}

INVOICE_TYPE_TO_PK: dict[str, str] = {
    "增值税专用发票": "1001ZZ1000000000SQ9Z",
    "增值税普通发票": "1001ZZ1000000000SQA1",
}

CITY_TYPE_TO_PK: dict[str, str] = {
    "公司负责人/一般地区": "1001W21000000001ZEYR",
    "公司负责人/省会直辖市": "1001W21000000001ZEYS",
    "公司负责人/北京上海广深": "1001W21000000001ZEYT",
    "其他人员/一般地区": "1001W21000000001ZEYU",
    "其他人员/省会直辖市": "1001W21000000001ZEYV",
    "其他人员/北京上海广深": "1001W21000000001ZEYW",
}

TRIP_TOOL_TO_PK: dict[str, str] = {
    "火车": "1001C110000000006HN2",
    "火车（过夜）": "1001C110000000006HN3",
    "长途巴士": "1001C110000000006HN4",
    "轮船": "1001C110000000006HN5",
}

YES_NO_TO_PK: dict[str, str] = {
    "是": "1001W21000000001XGK2",
    "否": "1001W21000000001XGK3",
}

TRAINING_FEE_TO_PK: dict[str, str] = {
    "否": "1001ZZ1000000000Y8SJ",
}

# Hints only — preflight requires exact dictionary keys (no silent rewrite).
INVOICE_TYPE_ALIASES: dict[str, str] = {
    "普票": "增值税普通发票",
    "普通发票": "增值税普通发票",
    "增值税普票": "增值税普通发票",
    "专票": "增值税专用发票",
    "增值税专票": "增值税专用发票",
}
