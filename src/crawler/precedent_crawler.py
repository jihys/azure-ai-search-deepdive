"""
law.go.kr 판례/해석례 통합 크롤러

수집 대상 (https://law.go.kr/precSc.do — 판례·해석례 등 메뉴)
────────────────────────────────────────────────────────────────
1. LawPrecedentCrawler  — 판례           (https://law.go.kr/precSc.do)
2. HunjaeCrawler        — 헌재결정례     (https://law.go.kr/detcSc.do)
3. ExpCrawler           — 법제처해석례   (https://law.go.kr/expcSc.do)
4. AdmRulCrawler        — 행정심판재결례 (https://law.go.kr/allDeccSc.do)
5. TaxLawCrawler        — 세법해석례     (taxlaw.nts.go.kr — 별도 사이트)

1~4는 law.go.kr 웹 스크래핑 방식 사용
  목록: POST /{type}ScListR.do  → HTML 파싱
  상세: GET  /{type}InfoP.do?{type}Seq={id} → HTML 파싱

TaxLawCrawler는 taxlaw.nts.go.kr REST API 사용
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Generator

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}


# ─────────────────────────────────────────────────────────────────────────────
# 공통 베이스 — law.go.kr 웹 스크래핑
# ─────────────────────────────────────────────────────────────────────────────

class _BaseWebCrawler:
    """law.go.kr 웹 스크래핑 공통 로직

    서브클래스에서 반드시 정의:
      LIST_URL      — POST로 목록을 가져오는 URL
      LIST_PARAMS   — LIST_URL에 붙는 query params (dict)
      SEQ_FIELD     — 목록 li id에서 추출하는 Seq 필드명 (예: "precSeq")
      LI_PREFIX     — 목록 li의 id prefix (예: "licPrec")
      DETAIL_URL    — 상세 페이지 URL 패턴 (예: "https://www.law.go.kr/precInfoP.do")
      SOURCE_NAME   — 출처 레이블 (예: "판례")
    """

    BASE = "https://www.law.go.kr"
    PAGE_SIZE = 100

    LIST_URL: str = ""
    LIST_PARAMS: dict = {}
    SEQ_FIELD: str = ""
    LI_PREFIX: str = ""
    DETAIL_URL: str = ""
    SOURCE_NAME: str = ""

    def __init__(
        self,
        delay_list: float = 0.5,
        delay_detail: float = 0.5,
        timeout: int = 20,
    ):
        self.delay_list = delay_list
        self.delay_detail = delay_detail
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(_HEADERS)

    # ──────────────────────────────────────────────────────────────────────────
    # 내부 헬퍼
    # ──────────────────────────────────────────────────────────────────────────

    def _list_post(self, query: str = "*", page: int = 1, page_size: int = PAGE_SIZE) -> str:
        """목록 HTML 반환"""
        data = {
            "q": query,
            "section": "bdyText",
            "outmax": str(page_size),
            "pg": str(page),
            "p1": "", "p2": "", "p3": "",
            "d1": "", "d2": "",
            "dsort": "", "fsort": "", "csq": "",
        }
        resp = self._session.post(
            self.LIST_URL,
            params=self.LIST_PARAMS,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.text

    def _parse_total(self, html: str) -> int:
        soup = BeautifulSoup(html, "html.parser")
        # "총 <strong>172,339</strong>건" 패턴
        for strong in soup.select("strong"):
            text = strong.get_text(strip=True).replace(",", "")
            if text.isdigit():
                following = strong.next_sibling
                if following and "건" in str(following):
                    return int(text)
        # 폴백: 텍스트에서 직접 파싱
        m = re.search(r"([\d,]+)\s*건", soup.get_text())
        return int(m.group(1).replace(",", "")) if m else 0

    def _parse_list_items(self, html: str) -> list[dict]:
        """li 태그에서 seq + 제목 추출"""
        soup = BeautifulSoup(html, "html.parser")
        items = []
        for li in soup.select(f'li[id^="{self.LI_PREFIX}"]'):
            li_id = li.get("id", "")
            # licPrec67167 → 67167
            seq = li_id[len(self.LI_PREFIX):]
            title = li.get_text(" ", strip=True)
            # 맨 앞 숫자(순번) 제거: "1. 부가가치세부과처분취소 ..."
            title = re.sub(r"^\d+\.\s*", "", title)
            if seq:
                items.append({self.SEQ_FIELD: seq, "title_hint": title})
        return items

    def _get_detail_html(self, seq: str) -> str:
        resp = self._session.get(
            self.DETAIL_URL,
            params={self.SEQ_FIELD: seq},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.text

    # ──────────────────────────────────────────────────────────────────────────
    # 퍼블릭 메서드
    # ──────────────────────────────────────────────────────────────────────────

    def get_total_count(self, query: str = "*") -> int:
        html = self._list_post(query, page=1, page_size=1)
        return self._parse_total(html)

    def iter_list(
        self,
        query: str = "*",
        start_page: int = 1,
        max_pages: int | None = None,
    ) -> Generator[dict, None, None]:
        """목록을 페이지별로 순회하며 seq + title_hint 생성"""
        page = start_page
        while True:
            if max_pages and (page - start_page) >= max_pages:
                break
            try:
                html = self._list_post(query, page=page, page_size=self.PAGE_SIZE)
                items = self._parse_list_items(html)
                if not items:
                    break
                for item in items:
                    yield item
                page += 1
                time.sleep(self.delay_list)
            except requests.RequestException as e:
                logger.warning("목록 페이지 %d 오류: %s", page, e)
                break

    def parse_detail(self, html: str, seq: str) -> dict:
        """상세 HTML → 구조화된 dict. 서브클래스에서 오버라이드."""
        raise NotImplementedError

    def get_detail(self, seq: str) -> dict | None:
        try:
            html = self._get_detail_html(seq)
            return self.parse_detail(html, seq)
        except Exception as e:
            logger.warning("[%s] 상세 수집 실패 seq=%s: %s", self.SOURCE_NAME, seq, e)
            return None

    def crawl_all(
        self,
        query: str = "*",
        start_page: int = 1,
        max_pages: int | None = None,
        delay_detail: float | None = None,
    ) -> Generator[dict, None, None]:
        """목록 순회 + 상세 수집 후 yield"""
        delay = delay_detail if delay_detail is not None else self.delay_detail
        for item in self.iter_list(query=query, start_page=start_page, max_pages=max_pages):
            seq = item[self.SEQ_FIELD]
            doc = self.get_detail(seq)
            if doc:
                yield doc
            time.sleep(delay)

    # ──────────────────────────────────────────────────────────────────────────
    # 공통 파싱 유틸
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_sections(content_div) -> dict[str, str]:
        """【섹션명】 h4 기준으로 내용을 수집"""
        sections: dict[str, str] = {}
        current_key = None
        current_parts: list[str] = []

        for el in content_div.children:
            if not hasattr(el, "name"):
                continue
            if el.name == "h4":
                if current_key and current_parts:
                    sections[current_key] = " ".join(current_parts).strip()
                current_key = el.get_text(strip=True).strip("【】")
                current_parts = []
            elif current_key and el.name in ("p", "div", "ul", "ol", "table", "blockquote"):
                text = el.get_text(" ", strip=True)
                if text:
                    current_parts.append(text)

        if current_key and current_parts:
            sections[current_key] = " ".join(current_parts).strip()

        return sections

    @staticmethod
    def _extract_subtit(soup) -> str:
        subtit = soup.select_one(".subtit1")
        return subtit.get_text(strip=True) if subtit else ""

    @staticmethod
    def _extract_title(soup) -> str:
        h2 = soup.select_one("#contentBody h2, .viewwrap h2")
        return h2.get_text(strip=True) if h2 else ""


# ─────────────────────────────────────────────────────────────────────────────
# 1. 판례
# ─────────────────────────────────────────────────────────────────────────────

class LawPrecedentCrawler(_BaseWebCrawler):
    """대법원 판례 크롤러

    수집 필드: 사건명, 법원명, 선고일자, 사건번호, 판시사항, 판결요지,
              참조조문, 참조판례, 전문
    """

    LIST_URL = "https://www.law.go.kr/precScListR.do"
    LIST_PARAMS = {"menuId": "7", "subMenuId": "47", "tabMenuId": "213"}
    SEQ_FIELD = "precSeq"
    LI_PREFIX = "licPrec"
    DETAIL_URL = "https://www.law.go.kr/precInfoP.do"
    SOURCE_NAME = "판례"

    # 사건정보 파싱 패턴
    _CASE_RE = re.compile(
        r"\[(.+?)\s+(\d{4}\.\s*\d+\.\s*\d+\.)\s+선고\s+(\S+)\s+판결\]"
    )

    def parse_detail(self, html: str, seq: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")

        title = self._extract_title(soup)
        subtit = self._extract_subtit(soup)

        court = date = case_no = ""
        m = self._CASE_RE.search(subtit)
        if m:
            court, date, case_no = m.group(1), m.group(2), m.group(3)

        sections: dict[str, str] = {}
        content_div = soup.select_one("#conScroll")
        if content_div:
            sections = self._parse_sections(content_div)

        return {
            "seq": seq,
            "source": self.SOURCE_NAME,
            "사건명": title,
            "법원명": court,
            "선고일자": date,
            "사건번호": case_no,
            "판시사항": sections.get("판시사항", ""),
            "판결요지": sections.get("판결요지", ""),
            "참조조문": sections.get("참조조문", ""),
            "참조판례": sections.get("참조판례", ""),
            "전문": sections.get("전문", ""),
            "url": f"https://www.law.go.kr/precInfoP.do?precSeq={seq}",
        }


# ─────────────────────────────────────────────────────────────────────────────
# 2. 헌재결정례
# ─────────────────────────────────────────────────────────────────────────────

class HunjaeCrawler(_BaseWebCrawler):
    """헌법재판소 결정례 크롤러

    수집 필드: 사건명, 사건번호, 결정일자, 결정유형, 판시사항, 결정요지,
              심판대상조문, 참조조문, 참조판례, 전문
    """

    LIST_URL = "https://www.law.go.kr/detcScListR.do"
    LIST_PARAMS = {"menuId": "7", "subMenuId": "49", "tabMenuId": "225"}
    SEQ_FIELD = "detcSeq"
    LI_PREFIX = "licDetc"
    DETAIL_URL = "https://www.law.go.kr/detcInfoP.do"
    SOURCE_NAME = "헌재결정례"

    # [전원재판부 2002헌마522, 2003. 7. 24.]
    _CASE_RE = re.compile(
        r"\[(.+?)\s+([\d헌마가나다라바사아자차카타파하]+),\s*(\d{4}\.\s*\d+\.\s*\d+\.)[,\]]"
    )

    def parse_detail(self, html: str, seq: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")

        title = self._extract_title(soup)
        subtit = self._extract_subtit(soup)

        court = case_no = date = ""
        m = self._CASE_RE.search(subtit)
        if m:
            court, case_no, date = m.group(1), m.group(2), m.group(3)

        sections: dict[str, str] = {}
        content_div = soup.select_one("#conScroll")
        if content_div:
            sections = self._parse_sections(content_div)

        return {
            "seq": seq,
            "source": self.SOURCE_NAME,
            "사건명": title,
            "재판부": court,
            "사건번호": case_no,
            "결정일자": date,
            "판시사항": sections.get("판시사항", ""),
            "결정요지": sections.get("결정요지", ""),
            "심판대상조문": sections.get("심판대상조문", ""),
            "참조조문": sections.get("참조조문", ""),
            "참조판례": sections.get("참조판례", ""),
            "전문": sections.get("전문", ""),
            "url": f"https://www.law.go.kr/detcInfoP.do?detcSeq={seq}",
        }


# ─────────────────────────────────────────────────────────────────────────────
# 3. 법제처 법령해석례
# ─────────────────────────────────────────────────────────────────────────────

class ExpCrawler(_BaseWebCrawler):
    """법제처 법령해석례 크롤러

    수집 필드: 제목, 문서번호, 회시일자, 요청기관, 질의요지, 회답, 이유
    """

    LIST_URL = "https://www.law.go.kr/expcScListR.do"
    LIST_PARAMS = {"menuId": "7", "subMenuId": "51", "tabMenuId": "237"}
    SEQ_FIELD = "expcSeq"
    LI_PREFIX = "licExpc"
    DETAIL_URL = "https://www.law.go.kr/expcInfoP.do"
    SOURCE_NAME = "법제처해석례"

    # [법제처 18-0203, 2018. 4. 30., 대통령경호처]
    _CASE_RE = re.compile(
        r"\[법제처\s+([\d\-]+),\s*(\d{4}\.\s*\d+\.\s*\d+\.),\s*(.+?)\]"
    )

    def parse_detail(self, html: str, seq: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")

        title = self._extract_title(soup)
        subtit = self._extract_subtit(soup)

        doc_no = date = requester = ""
        m = self._CASE_RE.search(subtit)
        if m:
            doc_no, date, requester = m.group(1), m.group(2), m.group(3)

        sections: dict[str, str] = {}
        content_div = soup.select_one("#conScroll")
        if content_div:
            sections = self._parse_sections(content_div)

        return {
            "seq": seq,
            "source": self.SOURCE_NAME,
            "제목": title,
            "문서번호": doc_no,
            "회시일자": date,
            "요청기관": requester,
            "질의요지": sections.get("질의요지", ""),
            "회답": sections.get("회답", ""),
            "이유": sections.get("이유", ""),
            "url": f"https://www.law.go.kr/expcInfoP.do?expcSeq={seq}",
        }


# ─────────────────────────────────────────────────────────────────────────────
# 4. 행정심판 재결례
# ─────────────────────────────────────────────────────────────────────────────

class AdmRulCrawler(_BaseWebCrawler):
    """행정심판 재결례 크롤러

    수집 필드: 사건명, 사건번호, 재결일자, 재결기관, 재결결과,
              재결요지, 주문, 청구취지, 이유
    """

    LIST_URL = "https://www.law.go.kr/deccScListR.do"
    LIST_PARAMS = {"menuId": "7", "subMenuId": "53"}
    SEQ_FIELD = "deccSeq"
    LI_PREFIX = "licDecc"
    DETAIL_URL = "https://www.law.go.kr/deccInfoP.do"
    SOURCE_NAME = "행정심판재결례"

    # licDecc2528__360201 → deccSeq=2528
    # onclick: deccView('2528', '360201')
    # li id prefix에 __ 가 포함되어 있으므로 분리 처리
    _LI_RE = re.compile(r"licDecc(\d+)__")

    # [국민권익위원회 1998-01590, 1998. 5. 8., 인용]
    _CASE_RE = re.compile(
        r"\[(.+?)\s+([\d\-]+),\s*(\d{4}\.\s*\d+\.\s*\d+\.),\s*(.+?)\]"
    )

    def _parse_list_items(self, html: str) -> list[dict]:
        """행정심판은 li id가 licDecc{seq}__{exprId} 형태"""
        soup = BeautifulSoup(html, "html.parser")
        items = []
        seen = set()
        for li in soup.select('li[id^="licDecc"]'):
            li_id = li.get("id", "")
            m = self._LI_RE.match(li_id)
            if not m:
                continue
            seq = m.group(1)
            if seq in seen:
                continue
            seen.add(seq)
            title = re.sub(r"^\d+\.\s*", "", li.get_text(" ", strip=True))
            items.append({self.SEQ_FIELD: seq, "title_hint": title})
        return items

    def parse_detail(self, html: str, seq: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")

        title = self._extract_title(soup)
        subtit = self._extract_subtit(soup)

        org = case_no = date = result = ""
        m = self._CASE_RE.search(subtit)
        if m:
            org, case_no, date, result = m.group(1), m.group(2), m.group(3), m.group(4)

        sections: dict[str, str] = {}
        content_div = soup.select_one("#conScroll")
        if content_div:
            sections = self._parse_sections(content_div)

        return {
            "seq": seq,
            "source": self.SOURCE_NAME,
            "사건명": title,
            "사건번호": case_no,
            "재결일자": date,
            "재결기관": org,
            "재결결과": result,
            "재결요지": sections.get("재결요지", ""),
            "주문": sections.get("주문", ""),
            "청구취지": sections.get("청구취지", ""),
            "이유": sections.get("이유", ""),
            "url": f"https://www.law.go.kr/deccInfoP.do?deccSeq={seq}",
        }


# ─────────────────────────────────────────────────────────────────────────────
# 5. 국세청 세법해석례 (별도 사이트)
# ─────────────────────────────────────────────────────────────────────────────

class TaxLawCrawler:
    """국세청 세법해석례 크롤러 (taxlaw.nts.go.kr)

    POST /pd/USEPDA001L.do → JSON 목록
    GET  /pd/USEPDA002P.do?pdIdx={id} → HTML 상세
    """

    BASE = "https://taxlaw.nts.go.kr"
    LIST_URL = f"{BASE}/pd/USEPDA001L.do"
    DETAIL_URL = f"{BASE}/pd/USEPDA002P.do"
    SOURCE_NAME = "세법해석례"

    TAX_TYPES = {
        "법인세": "CORPPROF",
        "소득세": "INCMTAX",
        "부가가치세": "VATAX",
        "상속세": "INHTAX",
        "증여세": "GIFTTAX",
        "종합부동산세": "CMPRHLNDTAX",
        "양도소득세": "TRNSFINCM",
        "국세기본": "NATLTAXBASE",
    }

    def __init__(
        self,
        delay: float = 0.5,
        timeout: int = 20,
    ):
        self.delay = delay
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(_HEADERS)

    def get_total_count(self, tax_type: str = "CORPPROF", query: str = "") -> int:
        payload = {
            "pdClCd": tax_type,
            "searchType": "1",
            "searchStr": query,
            "pageIndex": 1,
            "pageUnit": 1,
        }
        resp = self._session.post(self.LIST_URL, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        return data.get("paginationInfo", {}).get("totalRecordCount", 0)

    def iter_list(
        self,
        tax_type: str = "CORPPROF",
        query: str = "",
        page_size: int = 100,
        max_pages: int | None = None,
    ) -> Generator[dict, None, None]:
        page = 1
        while True:
            if max_pages and page > max_pages:
                break
            payload = {
                "pdClCd": tax_type,
                "searchType": "1",
                "searchStr": query,
                "pageIndex": page,
                "pageUnit": page_size,
            }
            resp = self._session.post(self.LIST_URL, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("pdList", [])
            if not items:
                break
            for item in items:
                yield item
            page += 1
            time.sleep(self.delay)

    def get_detail(self, pd_idx: str) -> dict | None:
        try:
            resp = self._session.get(
                self.DETAIL_URL,
                params={"pdIdx": pd_idx},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            title_el = soup.select_one("h2, .title, #pdTitle")
            title = title_el.get_text(strip=True) if title_el else ""

            content = {}
            for dt in soup.select("dt"):
                dd = dt.find_next_sibling("dd")
                key = dt.get_text(strip=True)
                val = dd.get_text(" ", strip=True) if dd else ""
                if key and val:
                    content[key] = val

            return {
                "pdIdx": pd_idx,
                "source": self.SOURCE_NAME,
                "제목": title,
                **content,
                "url": f"{self.DETAIL_URL}?pdIdx={pd_idx}",
            }
        except Exception as e:
            logger.warning("[세법해석례] 상세 수집 실패 pdIdx=%s: %s", pd_idx, e)
            return None

    def crawl_all(
        self,
        tax_type: str = "CORPPROF",
        query: str = "",
        max_pages: int | None = None,
    ) -> Generator[dict, None, None]:
        for item in self.iter_list(tax_type=tax_type, query=query, max_pages=max_pages):
            pd_idx = str(item.get("pdIdx", ""))
            if not pd_idx:
                continue
            doc = self.get_detail(pd_idx)
            if doc:
                doc.update({
                    "세목": item.get("pdClNm", ""),
                    "문서번호": item.get("pdDcmtNo", ""),
                    "회시일자": item.get("pdDcmtDt", ""),
                })
                yield doc
            time.sleep(self.delay)


# ─────────────────────────────────────────────────────────────────────────────
# Blob Storage 업로드 유틸
# ─────────────────────────────────────────────────────────────────────────────

def upload_to_blob(
    documents: list[dict],
    container_name: str,
    prefix: str = "",
    connection_string: str | None = None,
    account_name: str | None = None,
) -> int:
    """문서 목록을 JSON으로 Blob Storage에 업로드. 업로드된 건수 반환."""
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import BlobServiceClient

    if connection_string:
        blob_service = BlobServiceClient.from_connection_string(connection_string)
    elif account_name:
        blob_service = BlobServiceClient(
            account_url=f"https://{account_name}.blob.core.windows.net",
            credential=DefaultAzureCredential(),
        )
    else:
        raise ValueError("connection_string 또는 account_name 중 하나를 지정하세요.")

    container = blob_service.get_container_client(container_name)
    try:
        container.create_container()
    except Exception:
        pass

    uploaded = 0
    for doc in documents:
        seq = doc.get("seq") or doc.get("pdIdx") or str(uploaded)
        source = doc.get("source", "unknown")
        blob_name = f"{prefix}{source}/{seq}.json" if prefix else f"{source}/{seq}.json"
        container.upload_blob(
            name=blob_name,
            data=json.dumps(doc, ensure_ascii=False, indent=2).encode("utf-8"),
            overwrite=True,
        )
        uploaded += 1

    return uploaded


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _make_crawlers() -> dict[str, _BaseWebCrawler | TaxLawCrawler]:
    return {
        "prec": LawPrecedentCrawler(),
        "detc": HunjaeCrawler(),
        "expc": ExpCrawler(),
        "admrul": AdmRulCrawler(),
        "tax": TaxLawCrawler(),
    }


if __name__ == "__main__":
    import argparse
    import os

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="law.go.kr 크롤러")
    parser.add_argument(
        "--source",
        choices=["prec", "detc", "expc", "admrul", "tax", "all"],
        default="prec",
        help="수집 유형 (all=전체)",
    )
    parser.add_argument("--query", default="*", help="검색어 (* = 전체)")
    parser.add_argument("--max-pages", type=int, default=None, help="최대 페이지 수")
    parser.add_argument("--count-only", action="store_true", help="건수만 출력")
    parser.add_argument("--output", help="결과를 저장할 JSONL 파일 경로")
    parser.add_argument("--blob-container", help="Blob Storage 컨테이너명")
    parser.add_argument("--blob-account", help="Storage 계정명 (Managed Identity 인증)")
    args = parser.parse_args()

    crawlers = _make_crawlers()
    targets = list(crawlers.keys()) if args.source == "all" else [args.source]

    for target in targets:
        crawler = crawlers[target]
        name = getattr(crawler, "SOURCE_NAME", target)

        if args.count_only:
            try:
                if isinstance(crawler, TaxLawCrawler):
                    print(f"{name}:")
                    for tax_name, tax_code in TaxLawCrawler.TAX_TYPES.items():
                        try:
                            cnt = crawler.get_total_count(tax_type=tax_code)
                            print(f"  {tax_name}: {cnt:,}건")
                        except Exception as e:
                            print(f"  {tax_name}: 조회 실패 ({e})")
                else:
                    cnt = crawler.get_total_count(args.query)
                    print(f"{name}: {cnt:,}건")
            except Exception as e:
                print(f"{name}: 조회 실패 ({e})")
            continue

        outfile = open(args.output, "a", encoding="utf-8") if args.output else None

        try:
            if isinstance(crawler, TaxLawCrawler):
                gen = crawler.crawl_all(max_pages=args.max_pages)
            else:
                gen = crawler.crawl_all(query=args.query, max_pages=args.max_pages)

            docs_batch: list[dict] = []
            for i, doc in enumerate(gen, 1):
                print(f"[{name}] {i}: {list(doc.values())[2][:60]}")
                if outfile:
                    outfile.write(json.dumps(doc, ensure_ascii=False) + "\n")
                docs_batch.append(doc)

            if args.blob_container and docs_batch:
                n = upload_to_blob(
                    docs_batch,
                    container_name=args.blob_container,
                    account_name=args.blob_account,
                )
                print(f"  Blob 업로드 완료: {n}건")
        finally:
            if outfile:
                outfile.close()
