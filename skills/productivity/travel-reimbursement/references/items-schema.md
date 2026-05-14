# 差旅明细 JSON 契约

`ITEMS_JSON` 文件结构。至少必须包含 `transports` / `hotels` / `subsidies` 中的一组。

## 顶层

| 字段 | 必填 | 写入 | 说明 |
|---|---|---|---|
| `summary` | 是 | head `zy` | 报销摘要 |
| `bill_date` | 否 | head `djrq` | 单据日期 YYYY-MM-DD，缺省=当天 |
| `training_fee` | 否 | head `zyx11` | 是否含培训费，默认 "否" |
| `transports` | — | 交通明细数组 | |
| `hotels` | — | 住宿明细数组 | |
| `subsidies` | — | 补贴明细数组 | |

## transports[]

| 字段 | 必填 | 写入 | 说明 |
|---|---|---|---|
| `departure_date` | 是 | `defitem1` | 出发日期 YYYY-MM-DD |
| `arrival_date` | 是 | `defitem2` | 到达日期 YYYY-MM-DD |
| `vehicle` | 是 | `defitem5` | 飞机（商务舱/经济舱）、火车（商务座/一等座/二等座）、出租车、公交/地铁、长途巴士、轮船、其他 |
| `invoice_form` | 是 | `defitem15` | 飞机行程单、火车电子报销凭证、火车纸质报销凭证、长途巴士、轮船、出租车报销凭证 |
| `invoice_no` | 是 | `defitem44` | 发票号 |
| `amount` | 是 | `vat_amount` / `amount` / `bbje` | 票面总价（含税） |
| `tax_amount` | 否 | `defitem46` `defitem48` / `tax_amount`=0 | 税额，缺省 0.00 |
| `receiver` | 否 | 收款人 | 缺省=报销人 |
| `bank_account` | 否 | 收款账户 | 缺省=dispatch 默认值 |

## hotels[]

| 字段 | 必填 | 写入 | 说明 |
|---|---|---|---|
| `city_type` | 是 | `defitem16` | 公司负责人/一般地区、公司负责人/省会直辖市、公司负责人/北京上海广深、其他人员/一般地区、其他人员/省会直辖市、其他人员/北京上海广深 |
| `purpose` | 否 | `defitem10` | 用途 |
| `days` | 是 | `defitem20` | 住宿天数 |
| `invoice_type` | 是 | `defitem35` | 增值税专用发票、增值税普通发票 |
| `invoice_no` | 是 | `defitem44` | 发票号 |
| `amount` | 是 | `vat_amount` / `amount` | 报销金额 |
| `tax_amount` | 否 | `defitem46` / `tax_amount`=0 | 税额，缺省 0.00 |
| `receiver` | 否 | 收款人 | 缺省=报销人 |
| `bank_account` | 否 | 收款账户 | 缺省=dispatch 默认值 |

## subsidies[]

| 字段 | 必填 | 写入 | 说明                                      |
|---|---|---|-----------------------------------------|
| `days` | 是* | `defitem9` | 出差天数。未提供时,基于 transports 日期推算参考值并确认（见下方） |
| `tool` | 是 | `defitem40` | 火车、火车（过夜）、长途巴士、轮船                       |
| `official_car_pickup` | 是 | `defitem36` | 是、否                                     |
| `hosted_by_counterparty` | 是 | `defitem37` | 是、否                                     |
| `standard` | 否 | 元/天 | 缺省=dispatch `subsidy.defitem11`；两者都缺则报错 |
| `amount` | 否 | 总金额 | 缺省=`standard × days`                    |

**补贴标准来源优先级**：`subsidies[].amount` > `subsidies[].standard` > `defaults.subsidy.defitem11`。dry-run 输出会标记 `standard_source ∈ {items, dispatch}`，绝不允许硬编码。

**出差天数推算**（`days` 标记为 是* 的含义）：

- 构造 ITEMS_JSON 时若 `days` 缺失且有 transports，展示日期范围供用户参考：`min(departure_date) ~ max(arrival_date)`，由用户告知天数。
- 无 transports 时直接索取，不推算。
- 脚本中 `days` 仍为 `require` 必填，推算发生在 Claude 写入 JSON 之前。

## 最小示例

```json
{
  "summary": "北京出差",
  "bill_date": "2026-05-13",
  "transports": [
    {
      "departure_date": "2026-05-04",
      "arrival_date": "2026-05-07",
      "vehicle": "火车（二等座）",
      "invoice_form": "火车电子报销凭证",
      "invoice_no": "T123",
      "amount": "500.00"
    }
  ],
  "hotels": [
    {
      "city_type": "其他人员/省会直辖市",
      "days": 2,
      "invoice_type": "增值税普通发票",
      "invoice_no": "H789",
      "amount": "600.00"
    }
  ],
  "subsidies": [
    {
      "days": 2,
      "tool": "火车",
      "official_car_pickup": "否",
      "hosted_by_counterparty": "否"
    }
  ]
}
```

更完整的多明细样例见 `har/sample_items.json`。

注：subsidies 中的 `days` 可省略，会展示 transports 日期范围供你确认（见上方推算规则）。
