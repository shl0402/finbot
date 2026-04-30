#!/usr/bin/env python3
"""
Self-contained stock prediction tool — designed to be called by an LLM.

Pipeline:
  1. Scrape real-time news  (manager.run_scraper_manager, mode="futunn_news")
  2. Label via Gemini LLM   (google.genai SDK + response_schema, matching main.py)
  3. Score sentiment        (FinBERT / lexicon — same as sam_ontology.ipynb)
  4. Apply ontology        (competitor=invert, match=pass — same as sam_ontology.ipynb)
  5. Aggregate to daily    (sentiment_mean + news_count per day + lag features)
  6. Fetch price features  (price_feature_engine.get_price_features)
  7. Run ensemble model    (ensemble_models.ModelLoader: GBM + LSTM + stacking)

All imports are from within the tools/ directory.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, AsyncGenerator


import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

# ── Ensure tools/ is on the path so local imports work ──────────────────────
_TOOLS_DIR = Path(__file__).parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

# ── Local tool imports ───────────────────────────────────────────────────────
from manager import run_scraper_manager               # news scraping
from price_feature_engine import get_price_features   # price features
from ensemble_models import ModelLoader                       # ensemble model

# google-genai (structured LLM calls — matching main.py's SignalEnrichmentPipeline)
try:
    from google import genai
    from google.genai import types

    _GEMINI_SDK = True
except ImportError:
    _GEMINI_SDK = False
    genai = None
    types = None

# ── Configuration ────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    load_dotenv(env_path)
except ImportError:
    pass

API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.5-flash-lite"

# System prompt — hardcoded from config.yaml
SYSTEM_PROMPT = """You are an expert quantitative finance AI. Your task is to analyze financial news titles and map them to a specific structural ontology relative to a TARGET STOCK.

ONTOLOGY:
This ontology defines how news sentiment is dynamically translated into actionable trading signals for a specific TARGET STOCK. It maps the economic relationship between the entity mentioned in the news and the target.

0. Direct Entity Events (The "Self")
News explicitly regarding the target stock itself.
* 0.1 Direct Fundamental (Match): Earnings reports, guidance updates, product launches, or management changes directly at the target company.
* 0.2 Direct Regulatory/Legal (Match): The target company wins/loses a lawsuit, faces fines, or receives direct government approval.
* 0.3 Corporate Action (Match): Stock splits, buybacks, or dividend announcements.
* 0.4 Analyst/Brokerage Rating (Match): Upgrades, downgrades, price target adjustments, or initiation of coverage by investment banks and research firms.

1. Horizontal Relationships (Competitors & Peers)
Entities fighting for the same market share or capital.
* 1.1 Zero-Sum Catalyst (Invert): Competitor captures a finite resource (contract, patent, exclusive rights).
* 1.2 Sector Tailwind/Headwind (Match): A peer proves a macro trend that lifts/drags the whole sector.
* 1.3 Capacity/Supply Destruction (Invert): A peer suffers a factory fire, ban, or bankruptcy (Target gains market share).
* 1.4 Substitution Threat (Invert): An adjacent industry creates a cheaper/better alternative to the target's product.

2. Vertical Relationships (Supply Chain)
Shocks traveling up and down the flow of goods.
* 2.1 Upstream Breakthrough/Expansion (Match): Supplier invents a cheaper process or expands capacity.
* 2.2 Upstream Supply Shock (Match): Supplier faces shortages, strikes, or tariffs.
* 2.3 Downstream Demand Shock (Match): Major buyer sees a massive surge/drop in end-user sales.
* 2.4 Downstream Insolvency/Churn (Match): Major client goes bankrupt or switches to a competitor.

3. Strategic Relationships (Ecosystem)
Entities whose success is tied to the target without being direct suppliers.
* 3.1 Complementary Goods (Match): Products bought together (e.g., EVs and Charging Stations).
* 3.2 Strategic Partners/JV (Match): Explicit R&D, distribution, or marketing partnerships.

4. Market Microstructure & Capital Flows
News regarding the structural buying/selling of the stock, independent of company fundamentals.
* 4.1 Institutional Capital Flow (Match): Significant buying/selling by funds (e.g., Southbound Capital, Hedge Funds).
* 4.2 Index/ETF Inclusion (Match): The target is added to or removed from a major market index.

* 0.0 No Relation / Noise: The news does not fit the ontology, lacks actionable connection, or is purely retrospective summary.

INSTRUCTIONS:
1. Analyze the provided News Title relative to the Target Stock.
2. Extract the names of any companies explicitly mentioned into the 'related_company' array.
3. Determine the relationship ID using the ontology.
4. Evaluate 'fixed_sentiment_applicable': Because our downstream pipeline uses a "dumb" fixed sentiment model that scores the WHOLE text, you must determine if it is safe to apply.
   - Set to TRUE if the headline's overall tone clearly matches the direction of the catalyst.
   - Set to FALSE if the headline is mixed, highly complex, or talks about a competitor winning while the target is losing (a fixed sentiment model will score this near 0.0, which breaks our math).
5. Unknown Entity Protocol: If a company is mentioned that you do not recognize, and the text does not provide enough context to determine if they are a competitor, supplier, or partner to the Target Stock's sector, you MUST classify the relation_id as "0.0". Do not guess.

Output strictly as JSON:
{
  "chain_of_thought": "Explanation of the economic logic.",
  "related_company": ["Company A", "Company B"],
  "relation_id": "1.2",
  "fixed_sentiment_applicable": true,
  "confidence_score": 0.95
}"""

# ── Entity Map — same logic as sam_ontology.ipynb Cell 1 ────────────────────
# Built from: (1) Excel column-sector competitors + (2) manual supplier/index/institution relations
# competitor = invert sentiment | supplier/match/index/institution = pass through unchanged
_ENTITY_MAP: dict[str, dict[str, str]] = {}

# Helper to populate from keywords dict
def _add_competitors(target: str, competitor_keywords: list[str]):
    if target not in _ENTITY_MAP:
        _ENTITY_MAP[target] = {}
    for kw in competitor_keywords:
        kw_lower = kw.lower()
        if kw_lower not in _ENTITY_MAP[target]:
            _ENTITY_MAP[target][kw_lower] = "competitor"

def _add_relation(target: str, entity_keyword: str, rel_type: str):
    if target not in _ENTITY_MAP:
        _ENTITY_MAP[target] = {}
    key = entity_keyword.lower()
    if key not in _ENTITY_MAP[target]:
        _ENTITY_MAP[target][key] = rel_type

# ── Full entity map — matching sam_ontology.ipynb Cell 1 ─────────────────────
# Technology / Internet
_ENTITIES = {
    "700":  ["腾讯", "Tencent", "微信", "WeChat", "王者荣耀", "riot", "RIOT", "网易", "NetEase", "百度", "Baidu", "阿里巴巴", "Alibaba", "字节跳动", "ByteDance", "京东", "JD.com", "美团", "Meituan", "拼多多", "Pinduoduo"],
    "1810": ["小米", "Xiaomi", "红米", "Redmi", "POCO", "荣耀", "HONOR", "OPPO", "vivo", "Realme", "OnePlus", "三星", "Samsung", "苹果", "Apple", "iPhone", "华为", "Huawei", "中兴", "ZTE", "联想", "Lenovo", "戴尔", "Dell", "惠普", "HP"],
    "1211": ["比亚迪", "BYD", "Tesla", "特斯拉", "蔚来", "NIO", "小鹏", "XPeng", "理想汽车", "Li Auto", "吉利", "Geely", "长城汽车", "Great Wall", "广汽", "GAC", "长安汽车", "上汽", "SAIC", "东风", "Dongfeng"],
    "9988": ["阿里巴巴", "Alibaba", "淘宝", "Taobao", "天猫", "Tmall", "京东", "JD.com", "拼多多", "Pinduoduo", "PDD", "字节跳动", "ByteDance", "美团", "Meituan", "腾讯", "Tencent", "快手", "Kuaishou", "百度", "Baidu"],
    "9618": ["京东", "JD.com", "阿里巴巴", "Alibaba", "拼多多", "Pinduoduo", "PDD", "美团", "Meituan", "当当", "Dangdang", "唯品会", "Vipshop", "苏宁", "Suning"],
    "3690": ["美团", "Meituan", "饿了么", "Ele.me", "阿里口碑", "Alibaba", "大众点评", "Dianping", "抖音", "TikTok", "快手", "Kuaishou", "小红书", "RED", "携程", "Trip.com"],
    "1024": ["快手", "Kuaishou", "抖音", "TikTok", "微信视频号", "WeChat Channels", "B站", "Bilibili", "哔哩哔哩", "BILIBILI", "小红书", "RED", "AcFun", "YouTube"],
    "9626": ["B站", "Bilibili", "哔哩哔哩", "BILIBILI", "抖音", "TikTok", "快手", "Kuaishou", "小红书", "RED", "AcFun", "YouTube", "西瓜视频", "腾讯视频", "WeTV"],
    "9888": ["百度", "Baidu", "谷歌", "Google", "必应", "Bing", "搜狗", "Sogou", "360搜索", "360 Search", "字节跳动", "ByteDance", "阿里巴巴", "Alibaba"],
    "20":   ["商汤", "SenseTime", "旷视", "Megvii", "云从", "CloudWalk", "依图", "Yitu", "海康威视", "Hikvision", "大华", "Dahua"],
    "763":  ["中兴通讯", "ZTE", "华为", "Huawei", "爱立信", "Ericsson", "诺基亚", "Nokia", "三星通信", "Samsung Networks", "烽火通信", "FiberHome", "爱立信"],
    "992":  ["联想", "Lenovo", "戴尔", "Dell", "惠普", "HP", "华硕", "ASUS", "宏碁", "Acer", "苹果", "Apple", "华为", "Huawei", "小米", "Xiaomi"],
    "285":  ["比亚迪电子", "BYD Electronic", "富士康", "Foxconn", "伟创力", "Flex", "捷普", "Jabil", "冠捷", "TPV", "三星电机", "Samsung Electro"],
    "2382": ["舜宇光学", "Sunny Optical", "丘钛科技", "Q-Tech", "AAC", "瑞声科技", "大立光", "Largan", "玉晶光", "Genius", "欧菲光", "Ofilm", "信利国际", "Truly"],
    "2018": ["瑞声科技", "AAC Tech", "歌尔股份", "GoerTech", "奋达科技", "Fenda", "国光电器", "GGEC"],
    "1415": ["高伟电子", "Cowell", "丘钛科技", "Q-Tech", "欧菲光", "Ofilm", "信利国际", "Truly"],
    "1347": ["华虹半导体", "Hua Hong", "中芯国际", "SMIC", "台积电", "TSMC", "联电", "UMC", "GlobalFoundries", "三星半导体", "Samsung Semiconductor"],
    "981":  ["中芯国际", "SMIC", "华虹半导体", "Hua Hong", "台积电", "TSMC", "联电", "UMC", "GlobalFoundries", "三星半导体", "Samsung Semiconductor", "英特尔", "Intel", "AMD"],
    "788":  ["中国铁塔", "China Tower", "中国通信服务", "China Comservice", "中通服", "中移铁通"],
    "1729": ["汇聚科技", "Huiju Tech", "富春科技", "Fuchun Tech", "长江通信", "Changjiang Comm"],
    # Auto
    "9868": ["XPeng", "小鹏", "理想汽车", "Li Auto", "蔚来", "NIO", "比亚迪", "BYD", "吉利", "Geely", "特斯拉", "Tesla"],
    "2015": ["理想汽车", "Li Auto", "小鹏", "XPeng", "蔚来", "NIO", "比亚迪", "BYD", "吉利", "Geely", "特斯拉", "Tesla"],
    "175":  ["吉利汽车", "Geely", "比亚迪", "BYD", "长城汽车", "Great Wall", "长安汽车", "上汽", "SAIC", "广汽", "GAC", "东风", "Dongfeng", "奇瑞", "Chery"],
    "2333": ["长城汽车", "Great Wall", "吉利", "Geely", "比亚迪", "BYD", "长安汽车", "上汽", "SAIC", "广汽", "GAC", "东风", "Dongfeng"],
    "9866": ["蔚来", "NIO", "小鹏", "XPeng", "理想汽车", "Li Auto", "比亚迪", "BYD", "特斯拉", "Tesla"],
    "489":  ["东风集团", "Dongfeng", "吉利", "Geely", "比亚迪", "BYD", "长城汽车", "Great Wall", "长安汽车", "上汽", "SAIC"],
    "2238": ["广汽集团", "GAC", "吉利", "Geely", "比亚迪", "BYD", "长城汽车", "Great Wall", "长安汽车", "上汽", "SAIC"],
    # Banks / Finance
    "5":    ["汇丰", "HSBC", "渣打", "Standard Chartered", "恒生", "Hang Seng", "中银香港", "BOCHK", "花旗", "Citibank", "摩根大通", "JPMorgan", "东亚银行", "Bank of East Asia"],
    "1398": ["工商银行", "ICBC", "建设银行", "CCB", "农业银行", "ABC", "中国银行", "BOC", "交通银行", "BoCOM", "招商银行", "CMB", "兴业银行", "CIB"],
    "939":  ["建设银行", "CCB", "工商银行", "ICBC", "农业银行", "ABC", "中国银行", "BOC", "交通银行", "BoCOM", "招商银行", "CMB"],
    "1288": ["农业银行", "ABC", "工商银行", "ICBC", "建设银行", "CCB", "中国银行", "BOC", "交通银行", "BoCOM", "招商银行", "CMB"],
    "3988": ["中国银行", "BOC", "工商银行", "ICBC", "建设银行", "CCB", "农业银行", "ABC", "交通银行", "BoCOM", "招商银行", "CMB"],
    "2318": ["中国平安", "Ping An", "中国人寿", "China Life", "太平洋保险", "CPIC", "友邦", "AIA", "新华保险", "New China Life", "人保", "PICC"],
    "2628": ["中国人寿", "China Life", "中国平安", "Ping An", "太平洋保险", "CPIC", "友邦", "AIA", "新华保险", "New China Life", "人保", "PICC"],
    "1299": ["友邦保险", "AIA", "保诚", "Prudential", "宏利", "Manulife", "安盛", "AXA", "永明", "Sun Life", "中国人寿", "China Life", "中国平安", "Ping An"],
    "388":  ["港交所", "HKEX", "香港交易所", "伦敦证券交易所", "LSE", "新加坡交易所", "SGX", "纳斯达克", "Nasdaq", "纽约证券交易所", "NYSE", "泛欧交易所", "Euronext"],
    "2388": ["中银香港", "BOCHK", "汇丰", "HSBC", "恒生", "Hang Seng", "渣打", "Standard Chartered", "东亚银行", "Bank of East Asia", "工银亚洲", "ICBC Asia"],
    "2588": ["中银航空租赁", "BOC Aviation", "国银租赁", "CDB Leasing", "中飞租赁", "China Aircraft Leasing", "招银租赁", "CMB Leasing"],
    # Insurance / Healthcare
    "1833": ["平安好医生", "Ping An Healthcare", "阿里健康", "Ali Health", "京东健康", "JD Health", "叮当健康", "Dingdang", "医思健康", "EC Healthcare"],
    "241":  ["阿里健康", "Ali Health", "平安好医生", "Ping An Healthcare", "京东健康", "JD Health", "叮当健康", "Dingdang", "1药网", "111"],
    "6618": ["京东健康", "JD Health", "阿里健康", "Ali Health", "平安好医生", "Ping An Healthcare", "叮当健康", "Dingdang", "医思健康", "EC Healthcare"],
    "2269": ["药明生物", "WuXi Biologics", "药明康德", "WuXi AppTec", "三星生物", "Samsung Biologics", "Lonza", "勃林格殷格翰", "BI", "辉瑞", "Pfizer", "诺华", "Novartis"],
    "2359": ["药明康德", "WuXi AppTec", "药明生物", "WuXi Biologics", "凯莱英", "Asymchem", "博腾股份", "Porton", "九洲药业", "Jiuzhou Pharma"],
    "1093": ["石药集团", "CSPC", "恒瑞医药", "Hengrui", "中国生物制药", "Sino Biopharm", "齐鲁制药", "Qilu", "扬子江", "Yangtze River", "复星医药", "Fosun Pharma"],
    "1177": ["中国生物制药", "Sino Biopharm", "恒瑞医药", "Hengrui", "石药集团", "CSPC", "信达生物", "Innovent", "百济神州", "BeiGene", "复星医药", "Fosun Pharma"],
    "1276": ["恒瑞医药", "Hengrui", "石药集团", "CSPC", "中国生物制药", "Sino Biopharm", "齐鲁制药", "Qilu", "翰森制药", "Hansoh", "海思科", "Haisco"],
    "9969": ["诺诚健华", "InnoCare", "康方生物", "Akeso", "信达生物", "Innovent", "百济神州", "BeiGene", "恒瑞医药", "Hengrui"],
    "1513": ["丽珠医药", "Livzon", "石药集团", "CSPC", "恒瑞医药", "Hengrui", "中国生物制药", "Sino Biopharm", "复星医药", "Fosun Pharma"],
    "3347": ["泰格医药", "Tigermed", "药明康德", "WuXi AppTec", "凯莱英", "Asymchem", "博腾股份", "Porton", "昭衍新药", "JOINN"],
    "1801": ["信达生物", "Innovent", "百济神州", "BeiGene", "康方生物", "Akeso", "诺诚健华", "InnoCare", "恒瑞医药", "Hengrui", "中国生物制药", "Sino Biopharm"],
    "3692": ["翰森制药", "Hansoh", "恒瑞医药", "Hengrui", "中国生物制药", "Sino Biopharm", "石药集团", "CSPC", "齐鲁制药", "Qilu"],
    "9926": ["康方生物", "Akeso", "信达生物", "Innovent", "百济神州", "BeiGene", "诺诚健华", "InnoCare", "恒瑞医药", "Hengrui"],
    "6160": ["百济神州", "BeiGene", "信达生物", "Innovent", "康方生物", "Akeso", "诺诚健华", "InnoCare", "恒瑞医药", "Hengrui", "中国生物制药", "Sino Biopharm"],
    "2252": ["微创机器人", "Microport", "威高股份", "Well High", "南微医学", "NCGM", "心脉医疗", "Endovastec", "沛嘉医疗", "Peijia"],
    "9660": ["地平线机器人", "Horizon Robotics", "寒武纪", "Cambricon", "华为海思", "HiSilicon", "英伟达", "NVIDIA", "Mobileye"],
    "9880": ["优必选", "UBTECH", "九号公司", "Ninebot", "石头科技", "Roborock", "科沃斯", "Ecovacs", "小米", "Xiaomi"],
    "2432": ["越疆科技", "DOBOT", "大族机器人", "Han's Robot", "遨博智能", "AUBO", "节卡机器人", "JAKA", "埃斯顿", "Estun"],
    # Consumer / Retail / Food
    "2020": ["安踏体育", "Anta", "李宁", "Li Ning", "361度", "361 Degrees", "特步", "Xtep", "阿迪达斯", "Adidas", "耐克", "Nike", "斯凯奇", "Skechers", "Puma"],
    "2331": ["李宁", "Li Ning", "安踏体育", "Anta", "361度", "361 Degrees", "特步", "Xtep", "阿迪达斯", "Adidas", "耐克", "Nike"],
    "291":  ["华润啤酒", "CR Beer", "青岛啤酒", "Tsingtao", "百威亚太", "Budweiser APAC", "百威", "Budweiser", "雪花啤酒", "Snow Beer", "燕京啤酒", "重庆啤酒", "珠江啤酒"],
    "168":  ["青岛啤酒", "Tsingtao", "华润啤酒", "CR Beer", "百威亚太", "Budweiser APAC", "燕京啤酒", "雪花啤酒", "Snow Beer", "重庆啤酒", "珠江啤酒", "惠泉啤酒"],
    "1876": ["百威亚太", "Budweiser APAC", "华润啤酒", "CR Beer", "青岛啤酒", "Tsingtao", "燕京啤酒", "雪花啤酒", "Snow Beer", "嘉士伯", "Carlsberg"],
    "9633": ["农夫山泉", "Nongfu Spring", "华润怡宝", "C. Estbon", "康师傅", "Tingyi", "统一企业", "Uni-President", "娃哈哈", "Wahaha", "景田", "GBT", "今麦郎"],
    "2319": ["蒙牛乳业", "Mengniu", "伊利股份", "Yili", "光明乳业", "Bright", "三元股份", "Sanyuan", "君乐宝", "Junlebao", "飞鹤", "Feihe", "澳优"],
    "590":  ["六福珠宝", "Luk Fook", "周大福", "Chow Tai Fook", "周生生", "Chow Sang Sang", "老铺黄金", "Laopu Gold", "金至尊", "King Prince"],
    "1929": ["周大福", "Chow Tai Fook", "六福珠宝", "Luk Fook", "周生生", "Chow Sang Sang", "老铺黄金", "Laopu Gold", "金至尊", "King Prince"],
    "116":  ["周生生", "Chow Sang Sang", "周大福", "Chow Tai Fook", "六福珠宝", "Luk Fook", "老铺黄金", "Laopu Gold"],
    "6181": ["老铺黄金", "Laopu Gold", "周大福", "Chow Tai Fook", "六福珠宝", "Luk Fook", "周生生", "Chow Sang Sang", "金至尊", "King Prince"],
    "220":  ["统一企业", "Uni-President", "康师傅", "Tingyi", "旺旺", "Want Want", "中国旺旺", "China Want Want", "康师傅", "Nissin"],
    "322":  ["康师傅", "Tingyi", "统一企业", "Uni-President", "旺旺", "Want Want", "今麦郎", "今麦郎食品", "白象", "Bai Xiang"],
    "881":  ["中升控股", "Zhongsheng", "永达汽车", "Yongda", "广汇宝信", "Autohome", "正通汽车", "Zhengtong", "和谐汽车", "China Harmony"],
    "2":    ["中电", "CLP", "中华电力", "电能实业", "Power Assets", "港灯", "HK Electric", "华润电力", "China Resources Power", "香港电灯"],
    "3":    ["香港中华煤气", "HK & China Gas", "Towngas", "港灯", "HK Electric", "中电", "CLP", "华润燃气", "China Resources Gas", "新奥能源", "ENN Energy"],
    "6":    ["电能实业", "Power Assets", "港灯", "HK Electric", "中电", "CLP", "电能", "长江基建", "CKI", "恒基阳光", "Henderson Land"],
    "836":  ["华润电力", "China Resources Power", "中电", "CLP", "港灯", "HK Electric", "大唐发电", "DT Power", "华能国际", "Huaneng", "国电电力", "SDIC"],
    "2380": ["中国电力", "China Power", "中电", "CLP", "华润电力", "CR Power", "大唐发电", "DT Power", "华能国际", "Huaneng", "国电电力", "SDIC"],
    "1038": ["长江基建", "CKI", "电能实业", "Power Assets", "港灯", "HK Electric", "中电", "CLP", "恒基集团", "Henderson Land"],
    "2688": ["新奥能源", "ENN Energy", "华润燃气", "China Resources Gas", "港华燃气", "Towngas China", "中国燃气", "China Gas", "昆仑能源", "Kunlun Energy"],
    "1193": ["华润燃气", "China Resources Gas", "新奥能源", "ENN Energy", "港华燃气", "Towngas China", "中国燃气", "China Gas", "昆仑能源", "Kunlun Energy"],
    "135":  ["昆仑能源", "Kunlun Energy", "新奥能源", "ENN Energy", "华润燃气", "China Resources Gas", "港华燃气", "Towngas China", "中国燃气", "China Gas"],
    "2638": ["港灯电力", "HK Electric", "中电", "CLP", "电能实业", "Power Assets", "华润电力", "China Resources Power"],
    "1199": ["中远海运港口", "COSCO Ports", "招商局港口", "China Merchants Port", "和记黄埔", "Hutchison", "嘉里物流", "Kerry", "上港集团", "SIPG"],
    "144":  ["招商局港口", "China Merchants Port", "中远海运港口", "COSCO Ports", "和记黄埔", "Hutchison", "嘉里物流", "Kerry", "盐田港", "Yantian Port"],
    "2618": ["京东物流", "JD Logistics", "顺丰速运", "SF Express", "中通快递", "ZTO Express", "韵达快递", "Yunda", "圆通速递", "YTO Express"],
    "2057": ["中通快递", "ZTO Express", "顺丰速运", "SF Express", "圆通速递", "YTO Express", "韵达快递", "Yunda", "申通快递", "STO Express", "极兔速递", "J&T Express"],
    "1519": ["极兔速递", "J&T Express", "顺丰速运", "SF Express", "中通快递", "ZTO Express", "圆通速递", "YTO Express", "韵达快递", "Yunda", "申通快递", "STO Express"],
    # Resources / Energy
    "26":   ["中海油", "CNOOC", "中石油", "PetroChina", "中石化", "Sinopec", "埃尼", "Eni", "雪佛龙", "Chevron", "康菲", "ConocoPhillips", "西方石油", "Occidental"],
    "883":  ["中海油", "CNOOC", "中石油", "PetroChina", "中石化", "Sinopec", "英国石油", "BP", "埃尼", "Eni", "壳牌", "Shell", "道达尔", "TotalEnergies"],
    "386":  ["中石化", "Sinopec", "中石油", "PetroChina", "中海油", "CNOOC", "英国石油", "BP", "埃尼", "Eni", "壳牌", "Shell", "道达尔", "TotalEnergies"],
    "857":  ["中石油", "PetroChina", "中石化", "Sinopec", "中海油", "CNOOC", "埃尼", "Eni", "雪佛龙", "Chevron", "康菲", "ConocoPhillips"],
    "1088": ["中国神华", "Shenhua", "中煤能源", "China Coal", "兖矿能源", "Yankuang", "伊泰煤炭", "Yitai", "陕西煤业", "Shaanxi Coal", "山西焦化", "潞安环能"],
    "1171": ["兖矿能源", "Yankuang", "中国神华", "Shenhua", "中煤能源", "China Coal", "伊泰煤炭", "Yitai", "陕西煤业", "Shaanxi Coal"],
    "1898": ["中煤能源", "China Coal", "中国神华", "Shenhua", "兖矿能源", "Yankuang", "伊泰煤炭", "Yitai", "陕西煤业", "Shaanxi Coal"],
    "2600": ["中国铝业", "Chalco", "中国宏桥", "China Hongqiao", "南山铝业", "Nanshan Aluminum", "神火股份", "Shenhuo", "云铝股份", "Yun铝"],
    "1378": ["中国宏桥", "China Hongqiao", "中国铝业", "Chalco", "南山铝业", "Nanshan Aluminum", "神火股份", "Shenhuo", "云铝股份", "Yun铝"],
    "2899": ["紫金矿业", "Zijin Mining", "中国黄金", "China Gold", "山东黄金", "Shandong Gold", "招金矿业", "Zhaojin", "中金黄金", "CIMC Gold", "湖南黄金"],
    "1787": ["山东黄金", "Shandong Gold", "紫金矿业", "Zijin Mining", "招金矿业", "Zhaojin", "中国黄金", "China Gold", "恒兴黄金", "恒兴"],
    "1818": ["招金矿业", "Zhaojin", "紫金矿业", "Zijin Mining", "中国黄金", "China Gold", "山东黄金", "Shandong Gold", "恒兴黄金"],
    "3330": ["灵宝黄金", "Lingbao Gold", "紫金矿业", "Zijin Mining", "中国黄金", "China Gold", "山东黄金", "Shandong Gold", "招金矿业"],
    # Gaming / Internet content
    "9999": ["网易", "NetEase", "腾讯", "Tencent", "完美世界", "Perfect World", "盛趣游戏", "Shengqu Games", "米哈游", "miHoYo", "莉莉丝", "Lilith"],
    "1698": ["腾讯音乐", "Tencent Music", "网易云音乐", "NetEase Cloud Music", "Spotify", "Apple Music", "喜马拉雅", "Ximalaya", "荔枝", "Litchi"],
    "9898": ["网易云音乐", "NetEase Cloud Music", "腾讯音乐", "Tencent Music", "QQ音乐", "Spotify", "Apple Music", "喜马拉雅", "Ximalaya", "荔枝", "Litchi"],
    "772":  ["阅文集团", "China Literature", "掌阅科技", "Zhangyue", "中文在线", "China Literature Online", "起点中文", "Qidian"],
    "1357": ["美图", "Meitu", "字节跳动", "ByteDance", "快手", "Kuaishou", "小红书", "RED"],
    # Travel / Transport
    "9961": ["携程", "Trip.com", "去哪儿", "Qunar", "同程旅行", "Tongcheng", "艺龙", "eLong", "飞猪", "Fliggy", "马蜂窝", "MaFeng", "Booking", "Expedia"],
    "780":  ["同程旅行", "Tongcheng Travel", "携程", "Trip.com", "去哪儿", "Qunar", "飞猪", "Fliggy", "马蜂窝", "MaFeng", "Booking", "Expedia"],
    "293":  ["国泰航空", "Cathay Pacific", "香港航空", "HK Airlines", "大湾区航空", "Greater Bay Airlines", "中国国航", "Air China", "东方航空", "China Eastern"],
    "1919": ["中远海控", "COSCO Shipping", "东方海外", "OOCL", "中远海运港口", "COSCO Ports", "马士基", "Maersk", "赫伯罗特", "Hapag-Lloyd", "达飞", "CMA CGM"],
    "316":  ["东方海外国际", "OOCL", "中远海控", "COSCO Shipping", "中远海运港口", "COSCO Ports", "马士基", "Maersk", "赫伯罗特", "Hapag-Lloyd"],
    "1128": ["永利澳门", "Wynn Macau", "银河娱乐", "Galaxy Entertainment", "金沙中国", "Sands China", "美高梅中国", "MGM China", "澳博控股", "SJM", "新濠国际", "Melco"],
    "27":   ["银河娱乐", "Galaxy Entertainment", "金沙中国", "Sands China", "美高梅中国", "MGM China", "永利澳门", "Wynn Macau", "澳博控股", "SJM", "新濠国际", "Melco"],
    "1928": ["金沙中国", "Sands China", "银河娱乐", "Galaxy Entertainment", "美高梅中国", "MGM China", "永利澳门", "Wynn Macau", "澳博控股", "SJM", "新濠国际", "Melco"],
    "2282": ["美高梅中国", "MGM China", "银河娱乐", "Galaxy Entertainment", "金沙中国", "Sands China", "永利澳门", "Wynn Macau", "澳博控股", "SJM", "新濠国际", "Melco"],
    "880":  ["澳博控股", "SJM", "永利澳门", "Wynn Macau", "银河娱乐", "Galaxy Entertainment", "金沙中国", "Sands China", "美高梅中国", "MGM China"],
    "2200": ["万达酒店发展", "Wanda Hotel", "香格里拉", "Shangri-La", "华住集团", "Huazhu", "锦江酒店", "Jinjiang Hotels", "首旅酒店"],
    "1397": ["海丰国际", "SITC", "中远海控", "COSCO Shipping", "东方海外", "OOCL", "海能达", "Hytera"],
    "2314": ["波司登", "Bosideng", "加拿大鹅", "Canada Goose", "Moncler", "盟可睐", "七匹狼", "Septwolves", "红豆股份"],
    "2669": ["中海物业", "China Overseas Property", "绿城服务", "Greentown Service", "碧桂园服务", "Country Garden Services", "万物云", "Onewo"],
    "6098": ["碧桂园服务", "Country Garden Services", "万物云", "Onewo", "绿城服务", "Greentown Service", "中海物业", "China Overseas Property", "雅生活", "Yaha"],
    "6666": ["创梦天地", "iDreamSky", "中手游", "CMGE", "腾讯", "Tencent", "网易", "NetEase", "完美世界", "Perfect World"],
    "1811": ["中广核新能源", "CGN New Energy", "龙源电力", "Longyuan Power", "华能新能源", "Huaneng New Energy", "大唐新能源", "Datang Renewable"],
    "916":  ["民生银行", "CMBC", "招商银行", "CMB", "兴业银行", "CIB", "浦发银行", "SPD Bank", "平安银行", "Ping An Bank"],
    "9688": ["元宇宙云", "MetaCloud", "商汤", "SenseTime", "旷视", "Megvii", "百度", "Baidu"],
    "3898": ["亿航智能", "EHang", "小鹏汇天", "XPeng Aero", "峰飞航空", "AutoFlight", "Lilium", "Joby Aviation"],
    "9878": ["医思健康", "EC Healthcare", "香港医思", "Hong Kong Medical", "瑞尔齿科", "Arrail Dental", "通策医疗", "Tongci Medical"],
    "6899": ["长和外", "Changwaibao", "长江生命科技", "CK Life Sciences", "金斯瑞", "GenScript", "药明生物", "WuXi Biologics"],
    "9955": ["华立大学", "Huali Group", "中汇集团", "Zhonghui Group", "希望教育", "Hope Education", "宇华教育", "Yuhua Education"],
    "9950": ["鹰瞳科技", "Airdoc", "医脉通", "MediBo", "医渡云", "Yidu Cloud", "零氪科技", "LinkDoc"],
}

# Build entity map
for ticker, keywords in _ENTITIES.items():
    _ENTITY_MAP[ticker] = {kw.lower(): "competitor" for kw in keywords}

# Add supplier relations (matching sam_ontology.ipynb manual_relations)
_SUPPLIER_RELATIONS = [
    ("285", "981", "supplier"), ("285", "1347", "supplier"),
    ("2382", "981", "supplier"), ("2018", "981", "supplier"),
    ("1810", "981", "supplier"), ("1810", "1347", "supplier"),
    ("1810", "2382", "supplier"), ("1810", "2018", "supplier"),
    ("1415", "2382", "supplier"), ("700", "981", "supplier"), ("700", "1347", "supplier"),
    ("9626", "700", "supplier"), ("1024", "700", "supplier"), ("3690", "700", "supplier"),
    ("9988", "700", "supplier"), ("9618", "700", "supplier"),
    ("1211", "285", "supplier"), ("1211", "2382", "supplier"), ("1211", "2018", "supplier"),
    ("9868", "285", "supplier"), ("9868", "2382", "supplier"),
    ("2015", "285", "supplier"), ("2015", "2382", "supplier"),
    ("175", "285", "supplier"), ("175", "2382", "supplier"),
    ("2333", "285", "supplier"), ("2238", "285", "supplier"),
    ("9866", "285", "supplier"), ("489", "285", "supplier"),
    ("2", "1088", "supplier"), ("2", "1171", "supplier"), ("2", "386", "supplier"),
    ("3", "1088", "supplier"), ("3", "1171", "supplier"), ("3", "386", "supplier"),
    ("6", "1088", "supplier"), ("6", "1171", "supplier"), ("6", "386", "supplier"),
    ("836", "1088", "supplier"), ("836", "1171", "supplier"),
    ("2688", "1088", "supplier"), ("135", "1088", "supplier"),
    ("2638", "1088", "supplier"), ("1193", "1088", "supplier"),
    ("2380", "1088", "supplier"), ("1038", "1088", "supplier"),
    ("1919", "386", "supplier"), ("316", "386", "supplier"),
    ("1199", "386", "supplier"), ("144", "386", "supplier"),
    ("1177", "2269", "supplier"), ("1177", "2359", "supplier"),
    ("1093", "2269", "supplier"), ("1093", "2359", "supplier"),
    ("1276", "2269", "supplier"), ("1276", "2359", "supplier"),
    ("9969", "2269", "supplier"), ("1513", "2269", "supplier"),
    ("3347", "2269", "supplier"), ("1801", "2269", "supplier"),
    ("3692", "2269", "supplier"), ("9926", "2269", "supplier"),
    ("6160", "2269", "supplier"), ("241", "2269", "supplier"), ("6618", "2269", "supplier"),
    ("590", "2899", "supplier"), ("1929", "2899", "supplier"),
    ("116", "2899", "supplier"), ("6181", "2899", "supplier"),
    ("590", "1818", "supplier"), ("1929", "1818", "supplier"),
    ("116", "1818", "supplier"), ("6181", "1818", "supplier"),
    ("590", "1787", "supplier"), ("1929", "1787", "supplier"),
    ("116", "1787", "supplier"), ("6181", "1787", "supplier"),
    ("728", "763", "supplier"), ("762", "763", "supplier"), ("941", "763", "supplier"),
    ("728", "6869", "supplier"), ("762", "6869", "supplier"), ("941", "6869", "supplier"),
    ("728", "2342", "supplier"), ("762", "2342", "supplier"),
    ("9618", "2618", "supplier"),
    ("700", "981", "supplier"), ("700", "1347", "supplier"),
    ("9988", "981", "supplier"), ("9988", "1347", "supplier"),
]

# Add index constituents
_INDEX_MEMBERS = [
    "5", "388", "700", "9988", "3690", "1211", "1810", "2318", "939", "1398",
    "2388", "2", "3", "6", "883", "386", "857", "27", "1928", "2282",
    "291", "168", "1876", "2319", "2331", "2020", "2269", "1093", "1177",
    "2382", "992", "1088", "1171", "2899", "2600", "1919", "316", "9961",
    "780", "293", "135", "2688", "2638", "1193", "2380", "1038",
]

for ticker in _INDEX_MEMBERS:
    if ticker not in _ENTITY_MAP:
        _ENTITY_MAP[ticker] = {}
    if "hsi" not in _ENTITY_MAP[ticker]:
        _ENTITY_MAP[ticker]["hsi"] = "index"
    if "hang seng" not in _ENTITY_MAP[ticker]:
        _ENTITY_MAP[ticker]["hang seng"] = "index"

# Add southbound institutional
_SOUTHBOUND_MEMBERS = [
    "700", "9988", "3690", "9618", "1211", "1810", "2318", "5", "388",
]
for ticker in _SOUTHBOUND_MEMBERS:
    if ticker not in _ENTITY_MAP:
        _ENTITY_MAP[ticker] = {}
    if "southbound" not in _ENTITY_MAP[ticker]:
        _ENTITY_MAP[ticker]["southbound"] = "institution"

# Apply supplier relations
for t1, t2, rel in _SUPPLIER_RELATIONS:
    if t1 not in _ENTITY_MAP:
        _ENTITY_MAP[t1] = {}
    if t2 in _ENTITIES:
        for kw in _ENTITIES[t2]:
            key = kw.lower()
            if key not in _ENTITY_MAP[t1]:
                _ENTITY_MAP[t1][key] = rel


# ── LLM Labeler (matching main.py's SignalEnrichmentPipeline) ─────────────────

class LLMLabeler:
    """
    Labels news headlines via Gemini SDK using response_schema.
    Exactly matches main.py's SignalEnrichmentPipeline behavior.
    """

    RESPONSE_SCHEMA = {
        "type": "OBJECT",
        "properties": {
            "chain_of_thought": {"type": "STRING"},
            "related_company": {"type": "ARRAY", "items": {"type": "STRING"}},
            "relation_id": {"type": "STRING"},
            "fixed_sentiment_applicable": {"type": "BOOLEAN"},
            "confidence_score": {"type": "NUMBER"},
        },
        "required": [
            "chain_of_thought", "related_company", "relation_id",
            "fixed_sentiment_applicable", "confidence_score",
        ],
    }

    def __init__(self, api_key: str, model_name: str = GEMINI_MODEL, max_concurrent: int = 5):
        self.api_key = api_key
        self.model_name = model_name
        self._client = None
        self._semaphore = None
        self._config = None
        self._available = False
        self._init_error: str | None = None

        if not _GEMINI_SDK:
            self._init_error = "google-genai package not installed. Install with: pip install google-genai"
            print(f"[LLMLabeler] ERROR: {self._init_error}")
            return

        # Strip whitespace so key is not silently rejected due to trailing newline
        api_key = api_key.strip()

        if not api_key or api_key == "YOUR_GEMINI_API_KEY_HERE":
            self._init_error = "API key not set or still contains placeholder 'YOUR_GEMINI_API_KEY_HERE'. Set it at the top of test.py."
            print(f"[LLMLabeler] ERROR: {self._init_error}")
            return

        try:
            self._client = genai.Client(api_key=api_key)
            self._semaphore = asyncio.Semaphore(max_concurrent)
            self._config = types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=self.RESPONSE_SCHEMA,
            )
            self._available = True
            print(f"[LLMLabeler] Initialized successfully. Model: {model_name}")
        except Exception as e:
            self._init_error = f"Failed to initialize Gemini client: {e}"
            print(f"[LLMLabeler] ERROR: {self._init_error}")
            self._available = False

    def _check_ready(self) -> None:
        """Raise a RuntimeError if the labeler is not usable. Call at the top of label_news."""
        if not self._available:
            raise RuntimeError(
                f"[LLMLabeler] Cannot label news — {self._init_error or 'unknown error'}. "
                "Fix the issue above and re-run."
            )

    async def _label_one(self, item: dict, ticker: str, index: int, max_retries: int = 1) -> dict | None:
        prompt = (
            f"Target Stock: {ticker}\n"
            f"Target Sector: Unknown\n"
            f"News Title: {item.get('title', '')}"
        )

        # ── Attempt loop (1 initial + up to max_retries retries) ──────────────────
        last_error: Exception | None = None
        for attempt in range(1 + max_retries):
            try:
                async with self._semaphore:
                    response = await asyncio.wait_for(
                        self._client.aio.models.generate_content(
                            model=self.model_name,
                            contents=prompt,
                            config=self._config,
                        ),
                        timeout=30.0,
                    )
                llm_output = json.loads(response.text)
                item["relation_id"] = str(llm_output.get("relation_id", "0.0"))
                item["fixed_sentiment_applicable"] = bool(llm_output.get("fixed_sentiment_applicable", True))
                item["related_company"] = list(llm_output.get("related_company", []))
                item["chain_of_thought"] = str(llm_output.get("chain_of_thought", ""))
                item["confidence_score"] = float(llm_output.get("confidence_score", 0.5))
                item["llm_skipped"] = False
                print(f"  [{index}] OK: rel_id={item['relation_id']} | fixed_sentiment={item['fixed_sentiment_applicable']} "
                      f"| related={item['related_company']} | confidence={item['confidence_score']:.2f}")
                return item
            except asyncio.TimeoutError:
                last_error = None
                print(f"  [{index}] Attempt {attempt+1}: TIMEOUT (>30s).", end="")
                if attempt < max_retries:
                    print(" Retrying...")
                else:
                    print(" Skipping item.")
                break  # Don't retry timeouts
            except json.JSONDecodeError as e:
                last_error = None
                print(f"  [{index}] Attempt {attempt+1}: PARSE ERROR ({e}). Skipping item.")
                break
            except Exception as e:
                last_error = e
                err_type = type(e).__name__
                # Retry on 503 / 429 (rate limit) — transient errors
                if getattr(e, "code", None) in (503, 429) or "503" in str(e) or "429" in str(e):
                    print(f"  [{index}] Attempt {attempt+1}: {err_type} ({e}). Retrying...")
                    await asyncio.sleep(2)
                    continue
                # All other errors: skip immediately
                print(f"  [{index}] Attempt {attempt+1}: {err_type} ({e}). Skipping item.")
                break

        # ── All retries exhausted — mark as skipped ─────────────────────────────
        item["relation_id"] = "SKIP"
        item["fixed_sentiment_applicable"] = False
        item["related_company"] = []
        item["chain_of_thought"] = f"LLM failed after {1 + max_retries} attempt(s): {last_error}"
        item["confidence_score"] = 0.0
        item["llm_skipped"] = True
        return None

    async def label_news(self, news_items: list[dict], ticker: str) -> list[dict]:
        if not news_items:
            return []
        self._check_ready()  # Raises RuntimeError if LLM is not usable
        print(f"[LLMLabeler] Labeling {len(news_items)} headlines with Gemini...")
        tasks = [
            self._label_one(item.copy(), ticker=ticker, index=i + 1)
            for i, item in enumerate(news_items)
        ]
        results: list[dict | None] = await asyncio.gather(*tasks)
        # Filter out items the LLM failed to label
        labeled = [r for r in results if r is not None]
        skipped = len(results) - len(labeled)
        print(f"[LLMLabeler] Done. {len(labeled)} headlines labeled, {skipped} skipped.")
        return labeled


# ── Sentiment Analyzer (same as sam_ontology.ipynb Cell 0) ───────────────────

class SentimentAnalyzer:
    """
    FinBERT with TextBlob/lexicon fallback.
    Exactly matches sam_ontology.ipynb Cell 0 — same pos/neg word lists,
    same probability computation, same fallback logic.
    """

    def __init__(self):
        self.model = None
        self.pos_words = {
            "surge", "soar", "rally", "gain", "upgrade", "beat", "exceed",
            "growth", "profit", "bullish", "buy", "strong", "opportunity",
            "breakthrough", "positive", "record", "high", "rise", "increase",
            "outperform",
        }
        self.neg_words = {
            "drop", "fall", "decline", "downgrade", "miss", "below", "loss",
            "bearish", "sell", "weak", "risk", "warning", "negative", "low",
            "decrease", "plunge", "crash", "concern",
        }
        try:
            import torch
            from transformers import AutoTokenizer, AutoModelForSequenceClassification
            print("[SentimentAnalyzer] Loading FinBERT...")
            self.tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")
            self.model = AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert")
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            self.model.to(self.device)
            self.model.eval()
            self.labels = ["negative", "neutral", "positive"]
            print(f"[SentimentAnalyzer] FinBERT loaded on {self.device}")
        except Exception as e:
            print(f"[SentimentAnalyzer] FinBERT unavailable ({e}), using lexicon fallback.")
            self.model = None

    def get_sentiment(self, text: str) -> dict:
        if self.model is not None:
            try:
                import torch
                inputs = self.tokenizer(
                    text, return_tensors="pt", truncation=True, max_length=512
                )
                inputs = {k: v.to(self.device) for k, v in inputs.items()}
                with torch.no_grad():
                    probs = torch.nn.functional.softmax(
                        self.model(**inputs).logits, dim=-1
                    ).cpu().numpy()[0]
                return {
                    "sentiment": self.labels[int(probs.argmax())],
                    "score": float(probs[2] - probs[0]),
                    "positive_prob": float(probs[2]),
                    "negative_prob": float(probs[0]),
                    "neutral_prob": float(probs[1]),
                }
            except Exception:
                pass

        # Fallback (same logic as sam_ontology.ipynb)
        if pd.isna(text) or str(text).strip() == "":
            return {
                "sentiment": "neutral", "score": 0.0,
                "positive_prob": 0.0, "negative_prob": 0.0, "neutral_prob": 1.0,
            }
        text_lower = str(text).lower()
        pos_cnt = sum(1 for w in self.pos_words if w in text_lower)
        neg_cnt = sum(1 for w in self.neg_words if w in text_lower)
        total = pos_cnt + neg_cnt
        try:
            from textblob import TextBlob
            polarity = TextBlob(text).sentiment.polarity
        except Exception:
            polarity = 0.0
        if total == 0:
            final_polarity = polarity
        else:
            final_polarity = (pos_cnt - neg_cnt) / total
        if final_polarity > 0.1:
            sentiment = "positive"
        elif final_polarity < -0.1:
            sentiment = "negative"
        else:
            sentiment = "neutral"
        return {
            "sentiment": sentiment,
            "score": float(final_polarity),
            "positive_prob": float(max(0, final_polarity)),
            "negative_prob": float(max(0, -final_polarity)),
            "neutral_prob": float(1 - abs(final_polarity)),
        }


# ── Ontology Adjustment (same as sam_ontology.ipynb Cell 2) ──────────────────

def apply_ontology(items: list[dict], ticker: str) -> list[dict]:
    """
    Apply the financial knowledge graph ontology adjustment.
    Exactly matches sam_ontology.ipynb Cell 2:
      - competitor mentioned in title -> invert sentiment score
      - otherwise -> pass through unchanged (match)
    """
    ticker_map = _ENTITY_MAP.get(str(ticker), {})
    for item in items:
        raw = float(item.get("raw_sentiment_score", 0.0))
        title_lower = item.get("title", "").lower()
        adj = raw
        for kw, rel_type in ticker_map.items():
            if kw in title_lower:
                if rel_type == "competitor":
                    adj = -raw
                # supplier / index / institution -> match (adj = raw, unchanged)
                break
        item["ontology_sentiment"] = adj
    return items


# ── Daily Sentiment Builder ───────────────────────────────────────────────────

class DailySentimentBuilder:
    """
    Aggregates labeled/scored news into daily sentiment.
    Produces a DataFrame with the 8 sentiment columns matching sentiment_store.py:
      sentiment_mean, sentiment_lag_1, sentiment_lag_2, sentiment_lag_3,
      news_count, news_lag_1, news_lag_2, news_lag_3
    """

    def __init__(self, lookback: int = 20):
        self.lookback = lookback

    def _parse_date(self, date_str: str) -> datetime | None:
        if not date_str or date_str == "N/A":
            return None
        date_str = str(date_str).strip()

        # Relative / fuzzy strings (match before lowercasing so "April" is intact)
        date_lower = date_str.lower()
        if any(x in date_lower for x in ["hour", "minute", "just now", "ago"]):
            return datetime.now()
        if "day" in date_lower:
            m = re.search(r"(\d+)", date_str)
            if m:
                try:
                    return datetime.now() - timedelta(days=int(m.group(1)))
                except Exception:
                    pass
        if "week" in date_lower:
            m = re.search(r"(\d+)", date_str)
            if m:
                try:
                    return datetime.now() - timedelta(weeks=int(m.group(1)))
                except Exception:
                    pass

        # Explicit formats to try
        formats = [
            "%Y-%m-%d", "%Y/%m/%d",                     # 2026-04-29
            "%d/%m/%Y", "%m/%d/%Y",                   # 29/04/2026
            "%B %d, %Y", "%b %d, %Y",                 # April 29, 2026 / Apr 29, 2026
            "%d %B %Y", "%d %b %Y",                   # 29 April 2026
            "%B %d", "%b %d",                          # April 29 / Apr 29 (current year)
            "%d %B", "%d %b",                          # 29 April (current year)
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                # If no year was parsed, default to current year
                if dt.year == 1900:
                    dt = dt.replace(year=datetime.now().year)
                return dt
            except Exception:
                continue

        # Final fallback: dateparser
        try:
            import dateparser as _dp
            return _dp.parse(date_str)
        except Exception:
            pass
        return None

    def build(self, items: list[dict]) -> tuple[pd.DataFrame, dict]:
        """
        Build daily aggregation and return (sentiment_df, daily_summary).
        daily_summary maps date -> {"sentiment_mean": float, "news_count": int}
        """
        records = []
        for item in items:
            raw_time = item.get("time", "")
            dt = self._parse_date(raw_time)
            if dt is None:
                dt = datetime.now()
                print(f"       [DATE PARSE] Unparseable date: {repr(raw_time)} -> defaulting to today")
            # Defensive: ensure dt is a valid datetime (not pd.NaT or similar)
            if pd.isnull(dt):
                dt = datetime.now()
                print(f"       [DATE PARSE] Null date detected for {repr(raw_time)} -> defaulting to today")
            records.append({
                "date": dt.replace(hour=0, minute=0, second=0, microsecond=0),
                "sentiment_score": float(item.get("ontology_sentiment", 0.0)),
            })

        if not records:
            records = [{"date": datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
                        "sentiment_score": 0.0}]

        df = pd.DataFrame(records)
        daily_agg = df.groupby("date", as_index=False).agg(
            sentiment_mean=("sentiment_score", "mean"),
            news_count=("sentiment_score", "count"),
        ).sort_values("date").reset_index(drop=True)

        # Lag features (same as sentiment_store.py)
        for lag in [1, 2, 3]:
            daily_agg[f"sentiment_lag_{lag}"] = daily_agg["sentiment_mean"].shift(lag)
            daily_agg[f"news_lag_{lag}"] = daily_agg["news_count"].shift(lag)
        # Only drop rows where the core data columns are null (not lag cols,
        # which are NaN by design for the first 3 rows via shift())
        daily_agg = daily_agg.dropna(subset=["date", "sentiment_mean", "news_count"])

        sent_cols = ["sentiment_mean", "sentiment_lag_1", "sentiment_lag_2", "sentiment_lag_3",
                     "news_count", "news_lag_1", "news_lag_2", "news_lag_3"]

        # Pad to lookback days if needed
        if len(daily_agg) < self.lookback:
            padding_rows = self.lookback - len(daily_agg)
            pad_dates = [daily_agg["date"].min() - timedelta(days=i + 1) for i in range(padding_rows)]
            pad_data = {
                "date": pad_dates,
                "sentiment_mean": [0.0] * padding_rows,
                "news_count": [0] * padding_rows,
            }
            for lag in [1, 2, 3]:
                pad_data[f"sentiment_lag_{lag}"] = [0.0] * padding_rows
                pad_data[f"news_lag_{lag}"] = [0] * padding_rows
            pad_df = pd.DataFrame(pad_data)
            daily_agg = pd.concat([pad_df, daily_agg], ignore_index=True)
        elif len(daily_agg) > self.lookback:
            daily_agg = daily_agg.tail(self.lookback).reset_index(drop=True)

        # Daily summary dict for output
        daily_summary = {}
        for _, r in daily_agg.iterrows():
            date_val = r["date"]
            # Skip rows with null/NaT dates (shouldn't happen after the guard above, but be safe)
            if pd.isnull(date_val):
                print(f"       [DATE AGG] Skipping row with NaT date")
                continue
            date_key = str(date_val.date())
            daily_summary[date_key] = {
                "sentiment_mean": round(float(r["sentiment_mean"]), 4),
                "news_count": int(r["news_count"]),
            }

        return daily_agg[sent_cols].reset_index(drop=True), daily_summary


# ── Tool Function ─────────────────────────────────────────────────────────────

async def run_prediction(
    ticker: str,
    num_news: int = 30,
) -> AsyncGenerator[dict, None]:
    """
    Self-contained async-generator prediction tool — yields step events as they
    complete, then yields the final result dict.

    Each yielded item is one of:
      - {"step": <name>, "status": "start"|"complete"|"failed", "message": "...", ...kwargs}
      - ("result", <result_dict>)  — the final return value

    Example usage:
      async for event in run_prediction("AAPL"):
          if event[0] == "result":
              result = event[1]
          else:
              print(f"[{event['step']}] {event['status']} — {event['message']}")
    """
    print(f"\n{'='*60}")
    print(f"  [TOOL] Running prediction for ticker: {ticker}")
    print(f"{'='*60}\n")

    def _emit(step: str, status: str, **kwargs) -> dict:
        return {"step": step, "status": status, **kwargs}

    from datetime import datetime as _dt
    pipeline_start = _dt.utcnow().isoformat()

    # ── Step 1: Scrape news ───────────────────────────────────────────────
    yield _emit("news_scraping", "start",
         message="Scraping news via Futunn (last 20 days, max 2/day)...")
    print(f"[news_scraping] start  Scraping news via Futunn (last 20 days, max 2/day)...")
    raw_news = await asyncio.to_thread(
        run_scraper_manager, stock_name=ticker, mode="futunn_news_days",
        num_days=20, max_per_day=2
    )
    news_items: list[dict] = []
    if raw_news and isinstance(raw_news, list):
        for item in raw_news:
            news_items.append({
                "title":             item.get("title", ""),
                "time":              item.get("time", ""),
                "source":            item.get("source", ""),
                "link":              item.get("link", ""),
                "short_description": item.get("short_description", ""),
                "parsed_date":       item.get("parsed_date_str", ""),
            })
    yield _emit("news_scraping", "complete",
         message=f"Scraped {len(news_items)} items",
         count=len(news_items))
    print(f"[news_scraping] complete  Scraped {len(news_items)} items  count={len(news_items)}")

    # ── Step 2: LLM labeling ───────────────────────────────────────────────
    yield _emit("llm_labeling", "start",
         message=f"Labeling {len(news_items)} headlines via Gemini...")
    print(f"\n[llm_labeling] start  Labeling {len(news_items)} headlines via Gemini...")
    labeler = LLMLabeler(API_KEY)
    labeled = await labeler.label_news(news_items, ticker)
    yield _emit("llm_labeling", "complete",
         message=f"Labeled {len(labeled)} headlines",
         count=len(labeled))
    print(f"[llm_labeling] complete  Labeled {len(labeled)} headlines  count={len(labeled)}")

    # ── Step 3: Sentiment scoring ─────────────────────────────────────────
    yield _emit("sentiment", "start",
         message="Scoring sentiment (FinBERT / lexicon)...")
    print(f"\n[sentiment] start  Scoring sentiment (FinBERT / lexicon)...")
    analyzer = SentimentAnalyzer()
    for item in labeled:
        sent = analyzer.get_sentiment(item["title"])
        item["sentiment_label"]      = sent["sentiment"]
        item["raw_sentiment_score"]  = sent["score"]
        item["positive_prob"]        = sent["positive_prob"]
        item["negative_prob"]        = sent["negative_prob"]
        item["neutral_prob"]         = sent["neutral_prob"]
    yield _emit("sentiment", "complete",
         message=f"Scored {len(labeled)} items")
    print(f"[sentiment] complete  Scored {len(labeled)} items")

    # ── Step 4: Ontology adjustment ───────────────────────────────────────
    yield _emit("ontology", "start",
         message="Applying ontology adjustment (competitor=invert)...")
    print(f"\n[ontology] start  Applying ontology adjustment (competitor=invert)...")
    adjusted = apply_ontology(labeled, ticker)
    yield _emit("ontology", "complete",
         message=f"Adjusted {len(adjusted)} items",
         count=len(adjusted))
    print(f"[ontology] complete  Adjusted {len(adjusted)} items  count={len(adjusted)}")

    # ── Step 5: Daily aggregation ─────────────────────────────────────────
    yield _emit("daily_agg", "start",
         message="Building daily sentiment features (20-day lookback)...")
    print(f"\n[daily_agg] start  Building daily sentiment features (20-day lookback)...")
    builder = DailySentimentBuilder(lookback=20)
    sent_df, daily_summary = builder.build(adjusted)
    sent_df_dict = sent_df.to_dict(orient="records")
    parsed_dates = sorted(daily_summary.keys())
    latest_date  = parsed_dates[-1] if parsed_dates else None
    yield _emit("daily_agg", "complete",
         message=f"Built {len(parsed_dates)} daily rows",
         date_range=f"{parsed_dates[0] if parsed_dates else 'N/A'} → {latest_date or 'N/A'}",
         dates=parsed_dates)
    print(f"[daily_agg] complete  Built {len(parsed_dates)} daily rows  "
          f"date_range={parsed_dates[0] if parsed_dates else 'N/A'} → {latest_date or 'N/A'}")

    # ── Step 6: Price features ────────────────────────────────────────────
    yield _emit("price_fetch", "start",
         message="Fetching price features via yfinance...")
    print(f"\n[price_fetch] start  Fetching price features via yfinance...")
    try:
        from price_feature_engine import format_ticker
        raw_ticker = format_ticker(ticker)
        raw_data = yf.download(raw_ticker, period="6mo", progress=False)
        if not raw_data.empty:
            raw_dates = (
                pd.to_datetime(raw_data.index)
                .strftime("%Y-%m-%d")
                .tolist()
            )
        else:
            raw_dates = []

        price_df = get_price_features(ticker, lookback=20, fetch_days=100)
        price_cols = ["close", "Volume", "returns", "volatility_10d", "volume_change",
                      "price_range", "RSI", "MACD", "vwap", "hsi_volatility"]
        price_summary = {col: round(float(price_df[col].iloc[-1]), 4) for col in price_cols}
        price_df_dict = price_df.to_dict(orient="records")
        # Use the last N raw dates matching the lookback length
        price_dates = raw_dates[-len(price_df_dict):] if raw_dates else []

        # Extract OHLCV data from raw_data for the candlestick chart.
        # Flatten MultiIndex columns (yfinance returns (Price, Ticker) tuples).
        _ohlcv_df = raw_data.copy()
        if isinstance(_ohlcv_df.columns, pd.MultiIndex):
            _ohlcv_df.columns = _ohlcv_df.columns.get_level_values(0)
        _ohlcv_df.columns = [c.lower() if c != 'Volume' else 'volume' for c in _ohlcv_df.columns]
        _ohlcv_df = _ohlcv_df.reset_index()
        if 'date' not in _ohlcv_df.columns and 'Date' in _ohlcv_df.columns:
            _ohlcv_df.rename(columns={'Date': 'date'}, inplace=True)
        if 'date' in _ohlcv_df.columns:
            _ohlcv_df['date'] = pd.to_datetime(_ohlcv_df['date']).dt.strftime('%Y-%m-%d')
        _ohlcv_cols = ['date', 'open', 'high', 'low', 'close', 'volume']
        _ohlcv_available = [c for c in _ohlcv_cols if c in _ohlcv_df.columns]
        _ohlcv_last = _ohlcv_df[_ohlcv_available].iloc[-len(price_df_dict):].reset_index(drop=True)
        ohlcv_data = _ohlcv_last.to_dict(orient="records")
        # Round numeric values for cleaner JSON
        for row in ohlcv_data:
            for k, v in row.items():
                if isinstance(v, float):
                    row[k] = round(v, 4)
                elif isinstance(v, (int, np.integer)):
                    row[k] = int(v)

        yield _emit("price_fetch", "complete",
             message=f"Fetched {len(price_df)} price rows",
             rows=len(price_df),
             latest_close=price_summary["close"])
        print(f"[price_fetch] complete  Fetched {len(price_df)} price rows  "
              f"latest_close={price_summary['close']}")
    except Exception as e:
        yield _emit("price_fetch", "failed",
             message=f"Price fetch failed: {e}")
        print(f"[price_fetch] failed  {e}")
        raise

    # ── Step 7: Ensemble model prediction ─────────────────────────────────
    yield _emit("model", "start",
         message="Running ensemble model (GBM + LSTM + stacking)...")
    print(f"\n[model] start  Running ensemble model (GBM + LSTM + stacking)...")
    try:
        loader = ModelLoader()
        prob, signal = loader.predict_from_features(price_df, sent_df)
        yield _emit("model", "complete",
             message=f"Prediction: {signal} ({prob:.4f})",
             probability_up=round(float(prob), 4),
             signal=signal)
        print(f"[model] complete  Prediction: {signal} ({prob:.4f})  "
              f"probability_up={round(float(prob), 4)}  signal={signal}")
    except Exception as e:
        yield _emit("model", "failed",
             message=f"Model prediction failed: {e}")
        print(f"[model] failed  {e}")
        raise

    # ── Assemble full result ───────────────────────────────────────────────
    result = {
        "ticker": ticker,
        "metadata": {
            "pipeline_start":    pipeline_start,
            "pipeline_end":      _dt.utcnow().isoformat(),
            "news_scraped":      len(news_items),
            "headlines_labeled": len(labeled),
            "daily_rows":        len(sent_df),
            "price_rows":        len(price_df),
            "lookback_days":     20,
        },
        "raw_news": [
            {
                "title":             n["title"],
                "time":              n["time"],
                "source":            n["source"],
                "link":              n["link"],
                "short_description": n["short_description"],
                "parsed_date":       n["parsed_date"],
            }
            for n in news_items
        ],
        "news_items": [
            {
                "title":                      item["title"],
                "time":                       item["time"],
                "source":                     item["source"],
                "link":                       item["link"],
                "short_description":            item["short_description"],
                "parsed_date":               item.get("parsed_date", ""),
                "relation_id":                item["relation_id"],
                "fixed_sentiment_applicable": item["fixed_sentiment_applicable"],
                "related_company":           item["related_company"],
                "chain_of_thought":           item["chain_of_thought"],
                "confidence_score":         float(item["confidence_score"]),
                "sentiment_label":           item["sentiment_label"],
                "raw_sentiment_score":       round(float(item["raw_sentiment_score"]), 4),
                "positive_prob":             round(float(item["positive_prob"]), 4),
                "negative_prob":             round(float(item["negative_prob"]), 4),
                "neutral_prob":              round(float(item["neutral_prob"]), 4),
                "ontology_sentiment":         round(float(item["ontology_sentiment"]), 4),
            }
            for item in adjusted
        ],
        "daily_sentiment":  daily_summary,
        "sentiment_df_dict": sent_df_dict,
        "price_df_dict":    price_df_dict,
        "price_dates":      price_dates,
        "price_summary":    price_summary,
        "ohlcv_data":      ohlcv_data,
        "model_prediction": {
            "probability_up": round(float(prob), 4),
            "signal": signal,
        },
        "prediction_bar": {
            "signal": signal,
            "probability_up": round(float(prob), 4),
        },
    }

    print(f"\n{'='*60}")
    print(f"  [TOOL] RESULT: {signal}  (probability_up = {prob:.4f})")
    print(f"{'='*60}\n")
    yield _emit("done", "complete",
         probability_up=round(float(prob), 4),
         signal=signal)
    yield ("result", result)


# ── __main__ ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Stock prediction tool.")
    parser.add_argument("--ticker", "-t", type=str, default="1810",
                        help="Stock ticker (default: 1810 = Xiaomi)")
    parser.add_argument("--num-news", "-n", type=int, default=30,
                        help="Max news items to label (default 30)")
    parser.add_argument("--progress", action="store_true",
                        help="Show structured progress events on stderr as JSON")
    parser.add_argument("--json-output", action="store_true",
                        help="Output full result as JSON to stdout (suppresses pretty-print)")
    args = parser.parse_args()

    ticker = args.ticker.strip()
    if not ticker:
        print("Error: --ticker cannot be empty.")
        import sys
        sys.exit(1)

    try:
        async def run_and_print():
            result = None
            async for event in run_prediction(ticker, num_news=args.num_news):
                if isinstance(event, tuple) and event[0] == "result":
                    result = event[1]
                else:
                    step = event.get("step", "?")
                    status = event.get("status", "?")
                    msg = event.get("message", "")
                    count = event.get("count")
                    prob = event.get("probability_up")
                    signal = event.get("signal", "")
                    print(f"[{step}] {status}  {msg}", file=sys.stderr)
                    if count is not None:
                        print(f"       count={count}", file=sys.stderr)
                    if prob is not None:
                        print(f"       probability_up={prob:.4f}  signal={signal}", file=sys.stderr)
            return result

        result = asyncio.run(run_and_print())

        if args.json_output:
            # Pure JSON — for programmatic consumption (backend → frontend)
            print(json.dumps(result, indent=2, default=str))
        else:
            # Human-readable summary
            print("\n" + "=" * 60)
            print("  TOOL OUTPUT SUMMARY")
            print("=" * 60)

            mp = result["model_prediction"]
            print(f"\n[Model Prediction]")
            print(f"  Ticker:         {result['ticker']}")
            print(f"  Signal:         {mp['signal']}")
            print(f"  Probability UP: {mp['probability_up']}")

            print(f"\n[Metadata]")
            m = result["metadata"]
            print(f"  news_scraped={m['news_scraped']}  "
                  f"labeled={m['headlines_labeled']}  "
                  f"daily_rows={m['daily_rows']}  "
                  f"price_rows={m['price_rows']}")

            print(f"\n[Price Summary]")
            ps = result["price_summary"]
            print(f"  close={ps['close']} | volume={ps['Volume']} | "
                  f"returns={ps['returns']:.4f}")
            print(f"  volatility_10d={ps['volatility_10d']:.4f} | "
                  f"RSI={ps['RSI']:.2f} | MACD={ps['MACD']:.4f}")

            print(f"\n[News Items] ({len(result['news_items'])} total)")
            for i, n in enumerate(result["news_items"]):
                print(f"\n  [{i+1}] {n['title'][:100]}")
                print(f"       time={n['time']} | source={n['source']}")
                print(f"       relation_id={n['relation_id']} | "
                      f"fixed_sentiment={n['fixed_sentiment_applicable']}")
                print(f"       related_company={n['related_company']}")
                print(f"       sentiment={n['sentiment_label']} | "
                      f"raw_score={n['raw_sentiment_score']} | "
                      f"ontology_score={n['ontology_sentiment']}")
                print(f"       confidence={n['confidence_score']}")
                print(f"       chain_of_thought={n['chain_of_thought'][:120]}")

            print(f"\n[Daily Sentiment] ({len(result['daily_sentiment'])} days)")
            for date, vals in sorted(result["daily_sentiment"].items(), reverse=True):
                print(f"  {date}: sentiment_mean={vals['sentiment_mean']:.4f}  "
                      f"news_count={vals['news_count']}")

            print(f"\n[Sentiment DataFrame rows] ({len(result['sentiment_df_dict'])} rows)")
            print(f"[Price DataFrame rows] ({len(result['price_df_dict'])} rows)")
            print(f"[Raw News] ({len(result['raw_news'])} items)")

            print("\n[Full JSON output available in result dict for LLM tool calling]")
            print("Prediction completed successfully.")

    except Exception as e:
        import traceback
        print(f"\n[ERROR] Tool execution failed: {e}")
        traceback.print_exc()
        import sys
        sys.exit(1)
