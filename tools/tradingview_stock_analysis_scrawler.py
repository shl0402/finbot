from __future__ import annotations

import argparse
import json
import re
from typing import Dict, List, Optional

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright


BASE_URL = "https://www.tradingview.com"


def _clean_text(value: Optional[str]) -> str:
	"""Normalize whitespace and strip invisible unicode marks from scraped text."""
	if not value:
		return ""
	# TradingView values often include invisible directionality marks.
	value = re.sub(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069]", "", value)
	value = value.replace("\u202f", " ")
	return " ".join(value.split()).strip()


def _safe_text(page: Page, selector: str) -> str:
	locator = page.locator(selector)
	if locator.count() == 0:
		return ""
	return _clean_text(locator.first.inner_text())


def _first_non_empty_text(page: Page, selector: str) -> str:
	"""Return the first non-empty text from matching nodes."""
	locator = page.locator(selector)
	for i in range(locator.count()):
		text = _clean_text(locator.nth(i).inner_text())
		if text:
			return text
	return ""


def _safe_attr(page: Page, selector: str, attr: str) -> str:
	locator = page.locator(selector)
	if locator.count() == 0:
		return ""
	value = locator.first.get_attribute(attr)
	return _clean_text(value)


def _get_period_labels(page: Page) -> List[str]:
	labels: List[str] = []
	period_cells = page.locator(
		"div.container-OWKkVLyj div.values-AtxjAQkN > div.container-OxVAcLqi"
	)
	for i in range(period_cells.count()):
		cell = period_cells.nth(i)
		main_locator = cell.locator("div.value-OxVAcLqi")
		sub_locator = cell.locator("div.subvalue-OxVAcLqi")

		main_value = _clean_text(main_locator.first.inner_text()) if main_locator.count() > 0 else ""
		sub_value = _clean_text(sub_locator.first.inner_text()) if sub_locator.count() > 0 else ""
		if sub_value:
			labels.append(f"{main_value} ({sub_value})")
		else:
			labels.append(main_value)
	return labels


def _extract_stats_table(page: Page) -> Dict[str, Dict[str, str]]:
	periods = _get_period_labels(page)
	result: Dict[str, Dict[str, str]] = {}

	rows = page.locator("div.container-vKM0WfUu > div")
	current_group = "Ungrouped"

	for i in range(rows.count()):
		row = rows.nth(i)

		group_title = row.locator("div.groupTitle-C9MdAMrq")
		if group_title.count() > 0:
			current_group = _clean_text(group_title.first.inner_text()) or current_group
			if current_group not in result:
				result[current_group] = {}
			continue

		metric_name = row.get_attribute("data-name")
		if not metric_name:
			continue

		metric_name = _clean_text(metric_name)
		values: List[str] = []
		value_cells = row.locator("div.values-C9MdAMrq div.container-OxVAcLqi")

		for j in range(value_cells.count()):
			cell = value_cells.nth(j)
			value_locator = cell.locator("div.value-OxVAcLqi")
			value_text = _clean_text(value_locator.first.inner_text()) if value_locator.count() > 0 else ""

			# Some periods are paywalled and displayed as a lock icon instead of text.
			if not value_text and cell.locator("svg").count() > 0:
				value_text = "LOCKED"

			values.append(value_text)

		# Align metric values to known period labels when lengths differ.
		if len(values) < len(periods):
			values.extend([""] * (len(periods) - len(values)))
		if len(values) > len(periods):
			values = values[: len(periods)]

		result.setdefault(current_group, {})[metric_name] = {
			periods[k]: values[k] for k in range(len(periods))
		}

	return result


def _get_selected_period_type(page: Page) -> str:
	selected = page.locator("#financials-page-tabs button[aria-selected='true']")
	if selected.count() == 0:
		return "unknown"
	selected_id = _clean_text(selected.first.get_attribute("id"))
	if selected_id == "FQ":
		return "quarterly"
	if selected_id == "FY":
		return "annual"
	return selected_id or "unknown"


def _switch_period(page: Page, tab_id: str) -> None:
	tab = page.locator(f"#financials-page-tabs button#{tab_id}")
	if tab.count() == 0:
		return
	if _clean_text(tab.first.get_attribute("aria-selected")) == "true":
		return

	tab.first.click()
	page.wait_for_timeout(1200)


def scrape_tradingview_statistics(
	exchange: str,
	ticker: str,
	include_annual: bool = True,
	headless: bool = True,
) -> Dict:
	url = f"{BASE_URL}/symbols/{exchange}-{ticker}/financials-statistics-and-ratios/"

	with sync_playwright() as p:
		browser = p.chromium.launch(headless=headless)
		context = browser.new_context(
			viewport={"width": 1920, "height": 1080},
			user_agent=(
				"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
				"AppleWebKit/537.36 (KHTML, like Gecko) "
				"Chrome/122.0.0.0 Safari/537.36"
			),
		)
		page = context.new_page()
		page.goto(url, wait_until="domcontentloaded")

		try:
			page.wait_for_selector("div.container-vKM0WfUu", timeout=30000)
		except PlaywrightTimeoutError:
			browser.close()
			raise RuntimeError("Timed out waiting for TradingView statistics table to load.")

		data = {
			"source_url": url,
			"symbol": f"{exchange}:{ticker}",
			"company": {
				"name": _safe_text(page, "h2.title-HDE_EEoW"),
				"display_symbol": _safe_text(page, "span.item-xQqIQebY.textItem-xQqIQebY"),
				"exchange": _safe_text(page, "span.provider-xQqIQebY"),
			},
			"market": {
				"price": _first_non_empty_text(page, "span[data-qa-id='symbol-last-value'] span"),
				"currency": _first_non_empty_text(page, "span[data-qa-id='symbol-currency']"),
				"change": _first_non_empty_text(page, "div.change-zoF9r75I.js-symbol-change-direction span.js-symbol-change-pt"),
				"last_update": _first_non_empty_text(page, "span.js-symbol-lp-time"),
				"market_status": _safe_attr(page, "[data-qa-id='market-status-badge-button'] .content-VzJVlozY", "title"),
			},
			"statistics": {},
		}

		current_period_type = _get_selected_period_type(page)
		data["statistics"][current_period_type] = _extract_stats_table(page)

		if include_annual:
			_switch_period(page, "FY")
			annual_period_type = _get_selected_period_type(page)
			data["statistics"][annual_period_type] = _extract_stats_table(page)

			# Return to default tab to keep page interaction predictable.
			_switch_period(page, "FQ")

		browser.close()
		return data


def main() -> None:
	parser = argparse.ArgumentParser(
		description="Scrape TradingView Financial Statistics & Ratios data for a stock symbol."
	)
	parser.add_argument("--exchange", default="HKEX", help="Exchange code, e.g. HKEX")
	parser.add_argument("--ticker", default="1810", help="Ticker code, e.g. 1810 for Xiaomi")
	parser.add_argument(
		"--quarterly-only",
		action="store_true",
		help="Only scrape quarterly statistics (skip annual tab).",
	)
	parser.add_argument(
		"--headed",
		action="store_true",
		help="Run browser in headed mode (non-headless) for debugging.",
	)
	parser.add_argument(
		"--output",
		default="",
		help="Optional output JSON file path.",
	)
	args = parser.parse_args()

	result = scrape_tradingview_statistics(
		exchange=args.exchange,
		ticker=args.ticker,
		include_annual=not args.quarterly_only,
		headless=not args.headed,
	)

	rendered = json.dumps(result, indent=2, ensure_ascii=False)
	if args.output:
		with open(args.output, "w", encoding="utf-8") as f:
			f.write(rendered)
	print(rendered)


if __name__ == "__main__":
	# Default example requested by user: Xiaomi on HKEX (1810).
	main()
