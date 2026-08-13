# Reference & Open Datasets / 参考数据集

The shell needs no real data. These are the datasets to introduce in the
**algorithm-validation phase** to fit the generators (A1–A2) and run validation
(B1–B4). They double as the "reference dataset" named in a `GenerationSpec`.

## Warehouse / inventory / logistics (tabular + time series)

| Dataset | Use in framework | Notes |
|---------|------------------|-------|
| [Logistics & Supply Chain Dataset (Kaggle)](https://www.kaggle.com/datasets/datasetengineer/logistics-and-supply-chain-dataset) | A1, A2, C1 | shipments, demand, delays |
| [Smart Logistics Supply Chain (Kaggle)](https://www.kaggle.com/datasets/ziya07/smart-logistics-supply-chain-dataset) | A4, C3 | real-time asset tracking, IoT-style signals |
| [Logistics Warehouse Dataset (Kaggle)](https://www.kaggle.com/datasets/ziya07/logistics-warehouse-dataset) | A1, C2, C4 | demand, stock, layout, KPIs |
| [Global Product Inventory 2025 (Kaggle)](https://www.kaggle.com/datasets/keyushnisar/global-product-inventory-dataset-2025) | A1 | product master: stock, price, specs |
| [Inventory Management Dataset (Kaggle)](https://www.kaggle.com/datasets/hetulparmar/inventory-management-dataset) | A1, C1 | inventory movements |
| [Shipping/Logistics public datasets (GitHub)](https://github.com/austinlasseter/datasets-shipping-logistics) | A2, C1 | curated index of public logistics data |
| UCI **Online Retail II** (search UCI ML Repository) | A2, B1–B4, C1 | classic dated transactional demand; ideal for TSTR validation |
| M5 Forecasting (Walmart, Kaggle competition) | A2, C1 | hierarchical retail demand, strong forecasting benchmark |

## Synthetic-data tooling to adopt (algorithm phase)

| Tool | Role | Link |
|------|------|------|
| **SDV** (Synthetic Data Vault) | tabular / relational / time-series synthesis (CTGAN, TVAE, Gaussian Copula, HMA) | https://github.com/sdv-dev/SDV |
| **SDMetrics** | fidelity + quality reports (B1) | https://github.com/sdv-dev/SDMetrics |
| **SynthCity** | alternative synthesizers + privacy metrics (B3) | https://github.com/vanderschaarlab/synthcity |
| **DoppelGANger** | time-series / IoT sequence generation (A2, A4) | https://github.com/fjxmlzn/DoppelGANger |
| **Faker** | field-level fake values (already emulated in shell) | https://github.com/joke2k/faker |

## Multimodal / vision (reuse of prior work)

Reuse the existing fabric-defect / multimodal pipeline for C5 (shelf occupancy,
product/defect detection). Public bootstrap sets: MVTec AD (industrial defects),
SKU-110K / RetailProduct checkout images (dense retail shelves).

> ⚠️ Licensing: confirm each dataset's licence before commercial redistribution.
> For client delivery, prefer datasets permitting commercial use, or use them
> only to *fit generators* and ship the synthetic output.
