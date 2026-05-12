"""
법령 크롤러 - 국가법령정보센터(law.go.kr)에서 최근 개정 법령 데이터 수집
"""

import json
import os
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup


class LawCrawler:
    """국가법령정보센터 크롤러"""

    def __init__(self, base_url: str = "https://www.law.go.kr"):
        self.base_url = base_url
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def get_recent_laws(self, limit: int = 10) -> list[dict]:
        """최근 개정/공포 법령 목록 가져오기

        국가법령정보센터의 최근 제·개정 법령 페이지에서 데이터를 수집합니다.
        """
        laws = []
        try:
            # 최근 제·개정 법령 페이지
            url = f"{self.base_url}/LSW/lsSc.do?menuId=10&subMenuId=10&tabMenuId=tab9"
            print(f"[크롤링] 최근 법령 {limit}개 수집 시도: {url}")

            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            response.encoding = "utf-8"

            soup = BeautifulSoup(response.text, "html.parser")

            # 법령 목록 테이블에서 항목 추출
            law_rows = soup.select("table tbody tr")
            if not law_rows:
                # 대체 선택자 시도
                law_rows = soup.select(".list_02 li, .law_list li, .srchRstList li")

            for row in law_rows[:limit]:
                law_info = self._parse_law_row(row)
                if law_info:
                    laws.append(law_info)

            print(f"[크롤링] {len(laws)}개 법령 정보 수집 완료")

        except requests.RequestException as e:
            print(f"[크롤링 오류] 법령 목록 수집 실패: {e}")

        # 수집된 데이터가 없으면 Open API 시도
        if not laws:
            laws = self._get_laws_from_api(limit)

        # API도 실패하면 샘플 데이터 사용 (Lab 환경용)
        if not laws:
            print("[크롤링] 실제 사이트/API 수집 불가 → 샘플 법령 데이터를 생성합니다.")
            laws = self._generate_sample_laws(limit)

        return laws

    def _generate_sample_laws(self, limit: int) -> list[dict]:
        """Lab 환경용 샘플 법령 데이터 생성"""
        sample_laws = [
            {
                "id": "001954",
                "title": "개인정보 보호법",
                "url": "https://www.law.go.kr/법령/개인정보보호법",
                "pub_date": "2024-03-15",
            },
            {
                "id": "002100",
                "title": "인공지능 산업 육성 및 신뢰 확보에 관한 법률",
                "url": "https://www.law.go.kr/법령/인공지능산업육성법",
                "pub_date": "2025-01-21",
            },
            {
                "id": "001680",
                "title": "전자상거래 등에서의 소비자보호에 관한 법률",
                "url": "https://www.law.go.kr/법령/전자상거래법",
                "pub_date": "2024-06-20",
            },
            {
                "id": "001845",
                "title": "정보통신망 이용촉진 및 정보보호 등에 관한 법률",
                "url": "https://www.law.go.kr/법령/정보통신망법",
                "pub_date": "2024-09-15",
            },
            {
                "id": "002050",
                "title": "클라우드컴퓨팅 발전 및 이용자 보호에 관한 법률",
                "url": "https://www.law.go.kr/법령/클라우드컴퓨팅법",
                "pub_date": "2024-12-01",
            },
            {
                "id": "001920",
                "title": "데이터 산업진흥 및 이용촉진에 관한 기본법",
                "url": "https://www.law.go.kr/법령/데이터산업법",
                "pub_date": "2024-04-18",
            },
            {
                "id": "001750",
                "title": "전자정부법",
                "url": "https://www.law.go.kr/법령/전자정부법",
                "pub_date": "2024-07-01",
            },
            {
                "id": "002200",
                "title": "소프트웨어 진흥법",
                "url": "https://www.law.go.kr/법령/소프트웨어진흥법",
                "pub_date": "2025-02-10",
            },
            {
                "id": "001830",
                "title": "지능정보화 기본법",
                "url": "https://www.law.go.kr/법령/지능정보화기본법",
                "pub_date": "2024-08-25",
            },
            {
                "id": "002150",
                "title": "산업 디지털 전환 촉진법",
                "url": "https://www.law.go.kr/법령/산업디지털전환촉진법",
                "pub_date": "2025-01-05",
            },
        ]
        for law in sample_laws:
            law["crawled_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return sample_laws[:limit]

    def get_law_detail_sample(self, law: dict) -> dict:
        """샘플 법령에 대한 상세 내용 생성 (Lab 환경용)"""
        contents = {
            "001954": self._sample_privacy_law(),
            "002100": self._sample_ai_law(),
            "001680": self._sample_ecommerce_law(),
            "001845": self._sample_ict_law(),
            "002050": self._sample_cloud_law(),
            "001920": self._sample_data_law(),
            "001750": self._sample_egov_law(),
            "002200": self._sample_software_law(),
            "001830": self._sample_smart_info_law(),
            "002150": self._sample_digital_transform_law(),
        }
        content = contents.get(law["id"], self._sample_generic_law(law["title"]))
        markdown = self._convert_to_markdown(law["title"], content, law["id"])
        return {
            "id": law["id"],
            "title": law["title"],
            "content": content,
            "markdown": markdown,
            "url": law["url"],
            "crawled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    # ---- Sample law content generators ----

    def _sample_privacy_law(self) -> str:
        return """제1조(목적) 이 법은 개인정보의 처리 및 보호에 관한 사항을 정함으로써 개인의 자유와 권리를 보호하고, 나아가 개인의 존엄과 가치를 구현함을 목적으로 한다.

제2조(정의) 이 법에서 사용하는 용어의 뜻은 다음과 같다.
1. "개인정보"란 살아 있는 개인에 관한 정보로서 다음 각 목의 어느 하나에 해당하는 정보를 말한다.
  가. 성명, 주민등록번호 및 영상 등을 통하여 개인을 알아볼 수 있는 정보
  나. 해당 정보만으로는 특정 개인을 알아볼 수 없더라도 다른 정보와 쉽게 결합하여 알아볼 수 있는 정보
2. "처리"란 개인정보의 수집, 생성, 연계, 연동, 기록, 저장, 보유, 가공, 편집, 검색, 출력, 정정, 복구, 이용, 제공, 공개, 파기, 그 밖에 이와 유사한 행위를 말한다.
3. "정보주체"란 처리되는 정보에 의하여 알아볼 수 있는 사람으로서 그 정보의 주체가 되는 사람을 말한다.
4. "개인정보처리자"란 업무를 목적으로 개인정보파일을 운용하기 위하여 스스로 또는 다른 사람을 통하여 개인정보를 처리하는 공공기관, 법인, 단체 및 개인 등을 말한다.
5. "개인정보파일"이란 개인정보를 쉽게 검색할 수 있도록 일정한 규칙에 따라 체계적으로 배열하거나 구성한 개인정보의 집합물을 말한다.
6. "가명처리"란 개인정보의 일부를 삭제하거나 일부 또는 전부를 대체하는 등의 방법으로 추가 정보가 없이는 특정 개인을 알아볼 수 없도록 처리하는 것을 말한다.

제3조(개인정보 보호 원칙) ① 개인정보처리자는 개인정보의 처리 목적을 명확하게 하여야 하고, 그 목적에 필요한 범위에서 최소한의 개인정보만을 적법하고 정당하게 수집하여야 한다.
② 개인정보처리자는 개인정보의 처리 목적에 필요한 범위에서 적합하게 개인정보를 처리하여야 하며, 그 목적 외의 용도로 활용하여서는 아니 된다.
③ 개인정보처리자는 개인정보의 처리 목적에 필요한 범위에서 개인정보의 정확성, 완전성 및 최신성이 보장되도록 하여야 한다.
④ 개인정보처리자는 개인정보의 처리 방법 및 종류 등에 따라 정보주체의 권리가 침해받을 가능성과 그 위험 정도를 고려하여 개인정보를 안전하게 관리하여야 한다.

제4조(정보주체의 권리) 정보주체는 자신의 개인정보 처리와 관련하여 다음 각 호의 권리를 가진다.
1. 개인정보의 처리에 관한 정보를 제공받을 권리
2. 개인정보의 처리에 관한 동의 여부, 동의 범위 등을 선택하고 결정할 권리
3. 개인정보의 처리 여부를 확인하고 개인정보에 대하여 열람을 요구할 권리
4. 개인정보의 처리 정지, 정정·삭제 및 파기를 요구할 권리
5. 개인정보의 처리로 인하여 발생한 피해를 신속하고 공정한 절차에 따라 구제받을 권리

제15조(개인정보의 수집·이용) ① 개인정보처리자는 다음 각 호의 어느 하나에 해당하는 경우에는 개인정보를 수집할 수 있으며 그 수집 목적의 범위에서 이용할 수 있다.
1. 정보주체의 동의를 받은 경우
2. 법률에 특별한 규정이 있거나 법령상 의무를 준수하기 위하여 불가피한 경우
3. 공공기관이 법령 등에서 정하는 소관 업무의 수행을 위하여 불가피한 경우
4. 정보주체와의 계약의 체결 및 이행을 위하여 불가피하게 필요한 경우
5. 정보주체 또는 그 법정대리인이 의사표시를 할 수 없는 상태에 있거나 주소불명 등으로 사전 동의를 받을 수 없는 경우로서 명백히 정보주체 또는 제3자의 급박한 생명, 신체, 재산의 이익을 위하여 필요하다고 인정되는 경우

제17조(개인정보의 제공) ① 개인정보처리자는 다음 각 호의 어느 하나에 해당되는 경우에는 정보주체의 개인정보를 제3자에게 제공할 수 있다.
1. 정보주체의 동의를 받은 경우
2. 제15조제1항제2호·제3호·제5호 및 제39조의3제2항제2호·제3호에 따라 개인정보를 수집한 목적 범위에서 개인정보를 제공하는 경우

제28조의2(가명정보의 처리 등) ① 개인정보처리자는 통계작성, 과학적 연구, 공익적 기록보존 등을 위하여 정보주체의 동의 없이 가명정보를 처리할 수 있다.
② 개인정보처리자는 제1항에 따라 가명정보를 제3자에게 제공하는 경우에는 특정 개인을 알아보기 위하여 사용될 수 있는 정보를 포함하여서는 아니 된다.

제29조(안전조치의무) 개인정보처리자는 개인정보가 분실·도난·유출·위조·변조 또는 훼손되지 아니하도록 내부 관리계획 수립, 접속기록 보관 등 대통령령으로 정하는 바에 따라 안전성 확보에 필요한 기술적·관리적 및 물리적 조치를 하여야 한다.

제34조(개인정보 유출 통지 등) ① 개인정보처리자는 개인정보가 유출되었음을 알게 되었을 때에는 지체 없이 해당 정보주체에게 다음 각 호의 사실을 알려야 한다.
1. 유출된 개인정보의 항목
2. 유출된 시점과 그 경위
3. 유출로 인하여 발생할 수 있는 피해를 최소화하기 위하여 정보주체가 할 수 있는 방법 등에 관한 정보
4. 개인정보처리자의 대응 조치 및 피해 구제 절차
5. 정보주체에게 피해가 발생한 경우 신고 등을 접수할 수 있는 담당부서 및 연락처"""

    def _sample_ai_law(self) -> str:
        return """제1조(목적) 이 법은 인공지능 산업의 육성과 인공지능에 대한 신뢰 확보에 관한 사항을 규정함으로써 인공지능 기술의 발전과 산업 진흥을 촉진하고, 인공지능으로 인한 위험을 예방하여 국민의 삶의 질 향상과 국민경제의 발전에 이바지함을 목적으로 한다.

제2조(정의) 이 법에서 사용하는 용어의 뜻은 다음과 같다.
1. "인공지능"이란 인간의 학습, 추론, 지각, 판단, 자연어 처리 등의 지능적 행동을 구현하는 기술 또는 그 기술을 적용한 시스템을 말한다.
2. "인공지능 기술"이란 기계학습, 딥러닝, 자연어처리, 컴퓨터 비전, 음성인식, 로보틱스 등 인공지능을 구현하기 위한 제반 기술을 말한다.
3. "고위험 인공지능"이란 사람의 생명·신체의 안전, 기본권 보장에 중대한 영향을 미칠 수 있는 인공지능을 말한다.
4. "인공지능 사업자"란 인공지능 기술의 개발, 제공, 운영을 업으로 하는 자를 말한다.

제3조(기본원칙) ① 인공지능은 인간의 존엄성과 자율성을 존중하는 방향으로 개발·활용되어야 한다.
② 인공지능 기술의 개발과 활용에 있어 공정성, 투명성, 안전성, 책임성이 확보되어야 한다.
③ 인공지능으로 인하여 발생할 수 있는 차별이나 편향을 최소화하기 위한 노력을 하여야 한다.

제10조(인공지능 산업 진흥 기본계획) ① 과학기술정보통신부장관은 인공지능 산업의 육성을 위하여 5년마다 인공지능 산업 진흥 기본계획을 수립·시행하여야 한다.
② 기본계획에는 다음 각 호의 사항이 포함되어야 한다.
1. 인공지능 산업 진흥의 기본 방향
2. 인공지능 핵심 기술의 연구개발에 관한 사항
3. 인공지능 전문인력 양성에 관한 사항
4. 인공지능 데이터 구축 및 활용에 관한 사항
5. 인공지능 관련 중소기업 및 스타트업 지원에 관한 사항

제15조(고위험 인공지능의 관리) ① 고위험 인공지능을 개발·운영하는 자는 다음 각 호의 사항을 준수하여야 한다.
1. 인공지능의 의사결정 과정에 대한 설명 가능성 확보
2. 학습 데이터의 편향성 점검 및 시정
3. 인공지능 시스템의 안전성 테스트 실시
4. 이용자에 대한 인공지능 사용 사실 고지
5. 인공지능으로 인한 피해에 대한 구제절차 마련

제20조(인공지능 윤리기준) ① 정부는 인공지능 기술의 개발과 활용에 관한 윤리기준을 정하여 고시하여야 한다.
② 윤리기준에는 다음 각 호의 사항이 포함되어야 한다.
1. 인간의 존엄성 및 개인의 자율성 존중
2. 사회적 공정성 및 비차별
3. 기술의 투명성 및 설명 가능성
4. 안전성 및 보안성
5. 개인정보 및 프라이버시 보호"""

    def _sample_ecommerce_law(self) -> str:
        return """제1조(목적) 이 법은 전자상거래 및 통신판매 등에 의한 재화 또는 용역의 공정한 거래에 관한 사항을 규정함으로써 소비자의 권익을 보호하고 시장의 신뢰도를 높여 국민경제의 건전한 발전에 이바지함을 목적으로 한다.

제2조(정의) 이 법에서 사용하는 용어의 뜻은 다음과 같다.
1. "전자상거래"란 전자거래의 방법으로 상행위를 하는 것을 말한다.
2. "통신판매"란 우편·전기통신, 그 밖에 총리령으로 정하는 방법으로 재화 또는 용역의 판매에 관한 정보를 제공하고 소비자의 청약을 받아 재화 또는 용역을 판매하는 것을 말한다.
3. "통신판매업자"란 통신판매를 업으로 하는 자 또는 그와의 약정에 따라 통신판매업무를 수행하는 자를 말한다.
4. "통신판매중개"란 사이버몰의 이용을 허락하거나 그 밖에 총리령으로 정하는 방법으로 거래 당사자 간의 통신판매를 알선하는 행위를 말한다.

제13조(신원 및 거래조건에 대한 정보의 제공) ① 통신판매업자가 재화등을 판매하는 경우에는 그 재화등의 공급에 앞서 소비자가 그 표시·광고의 내용을 정확하게 이해하고 거래할 수 있도록 적절한 방법으로 다음 각 호의 사항에 관한 정보를 제공하여야 한다.
1. 재화등의 공급자 및 판매자의 상호, 대표자 성명, 주소, 전화번호
2. 재화등의 명칭·종류 및 내용
3. 재화등의 가격과 그 지급 방법 및 시기
4. 재화등의 공급 방법 및 시기

제17조(청약철회등) ① 통신판매업자와 재화등의 구매에 관한 계약을 체결한 소비자는 계약내용에 관한 서면을 받은 날부터 7일 이내에 그 청약의 철회 등을 할 수 있다.
② 소비자는 다음 각 호의 어느 하나에 해당하는 경우에는 통신판매업자의 의사에 반하여 청약철회등을 할 수 없다.
1. 소비자에게 책임있는 사유로 재화등이 멸실 또는 훼손된 경우
2. 소비자의 사용 또는 일부 소비에 의하여 재화등의 가치가 현저히 감소한 경우
3. 시간의 경과에 의하여 재판매가 곤란할 정도로 재화등의 가치가 현저히 감소한 경우"""

    def _sample_ict_law(self) -> str:
        return """제1조(목적) 이 법은 정보통신망의 이용을 촉진하고 정보통신서비스를 이용하는 자의 개인정보를 보호함과 아울러 정보통신망을 건전하고 안전하게 이용할 수 있는 환경을 조성하여 국민생활의 향상과 공공복리의 증진에 이바지함을 목적으로 한다.

제2조(정의) ① 이 법에서 사용하는 용어의 뜻은 다음과 같다.
1. "정보통신망"이란 전기통신설비를 이용하거나 전기통신설비와 컴퓨터 및 컴퓨터의 이용기술을 활용하여 정보를 수집·가공·저장·검색·송신 또는 수신하는 정보통신체계를 말한다.
2. "정보통신서비스"란 전기통신사업법에 따른 전기통신역무와 이를 이용하여 정보를 제공하거나 정보의 제공을 매개하는 것을 말한다.

제44조의7(불법정보의 유통금지 등) ① 누구든지 정보통신망을 통하여 다음 각 호의 어느 하나에 해당하는 정보를 유통하여서는 아니 된다.
1. 음란한 부호·문언·음향·화상 또는 영상을 배포·판매·임대하거나 공공연하게 전시하는 내용의 정보
2. 사람을 비방할 목적으로 공공연하게 사실이나 거짓의 사실을 드러내어 타인의 명예를 훼손하는 내용의 정보
3. 공포심이나 불안감을 유발하는 부호·문언·음향·화상 또는 영상을 반복적으로 상대방에게 도달하게 하는 내용의 정보

제48조(정보통신망 침해행위 등의 금지) ① 누구든지 정당한 접근권한 없이 또는 허용된 접근권한을 넘어 정보통신망에 침입하여서는 아니 된다.
② 누구든지 정당한 사유 없이 정보통신시스템, 데이터 또는 프로그램 등을 훼손·멸실·변경·위조하거나 그 운용을 방해할 수 있는 프로그램을 전달 또는 유포하여서는 아니 된다."""

    def _sample_cloud_law(self) -> str:
        return """제1조(목적) 이 법은 클라우드컴퓨팅의 발전 및 이용을 촉진하고 클라우드컴퓨팅서비스를 안전하게 이용할 수 있는 환경을 조성함으로써 국민생활의 향상과 국민경제의 발전에 이바지함을 목적으로 한다.

제2조(정의) 이 법에서 사용하는 용어의 뜻은 다음과 같다.
1. "클라우드컴퓨팅"이란 집적·공유된 정보통신기기, 정보통신설비, 소프트웨어 등 정보통신자원을 이용자의 요구나 수요 변화에 따라 정보통신망을 통하여 신축적으로 이용할 수 있도록 하는 정보처리체계를 말한다.
2. "클라우드컴퓨팅서비스"란 클라우드컴퓨팅을 활용하여 상용으로 타인에게 정보통신자원을 제공하는 서비스를 말한다.
3. "이용자"란 클라우드컴퓨팅서비스를 이용하는 자를 말한다.

제20조(클라우드컴퓨팅서비스 이용자 보호) ① 클라우드컴퓨팅서비스 제공자는 이용자의 정보를 보호하기 위하여 다음 각 호의 조치를 하여야 한다.
1. 이용자 정보의 보호를 위한 기술적·관리적 보호조치
2. 이용자 정보가 유출된 경우의 통지
3. 이용자 정보의 저장장소 등에 관한 정보 제공

제23조(이용자 정보의 보호) ① 클라우드컴퓨팅서비스 제공자는 법률에 특별한 규정이 있는 경우 또는 이용자의 동의가 있는 경우를 제외하고는 이용자의 정보를 제3자에게 제공하거나 서비스 제공 목적 외의 용도로 이용할 수 없다.
② 클라우드컴퓨팅서비스 제공자는 이용자의 정보를 제공하거나 열람할 수 있도록 허용한 경우에는 그 사실을 이용자에게 알려야 한다."""

    def _sample_data_law(self) -> str:
        return """제1조(목적) 이 법은 데이터의 생산, 거래 및 활용 촉진에 관하여 필요한 사항을 정함으로써 데이터산업 발전의 기반을 조성하고 데이터의 효율적 활용을 도모하여 국민경제의 발전에 이바지함을 목적으로 한다.

제2조(정의) 이 법에서 사용하는 용어의 뜻은 다음과 같다.
1. "데이터"란 다양한 부가가치 창출을 위하여 관찰, 실험, 조사, 수집 등으로 취득하거나 정보시스템 및 소프트웨어 기술 등을 통하여 생성된 것으로서 광 또는 전자적 방식으로 처리될 수 있는 자료 또는 정보를 말한다.
2. "데이터산업"이란 데이터의 수집·가공·분석·유통 등의 처리와 이를 활용한 서비스를 업으로 하는 산업을 말한다.
3. "데이터거래"란 데이터를 유무상으로 제공·교환하거나 그에 관한 알선·중개를 하는 행위를 말한다.

제12조(공공데이터 제공) ① 공공기관의 장은 데이터산업 진흥 및 이용 촉진을 위하여 공공데이터를 적극적으로 제공하여야 한다.
② 공공데이터 제공 시 기계판독이 가능한 형태로 제공하여야 하며, 가능한 한 개방형 표준에 따라야 한다.

제15조(데이터 품질관리) ① 데이터를 생산·제공하는 자는 데이터의 정확성, 최신성, 완전성을 유지하기 위하여 노력하여야 한다.
② 과학기술정보통신부장관은 데이터 품질관리에 관한 기준을 정하여 고시할 수 있다."""

    def _sample_egov_law(self) -> str:
        return """제1조(목적) 이 법은 행정업무의 전자적 처리를 위한 기본원칙, 절차 및 추진방법 등을 규정함으로써 전자정부를 효율적으로 구현하고, 행정의 생산성, 투명성 및 민주성을 높여 국민의 삶의 질을 향상시키는 것을 목적으로 한다.

제2조(정의) 이 법에서 사용하는 용어의 뜻은 다음과 같다.
1. "전자정부"란 정보기술을 활용하여 행정기관 및 공공기관의 업무를 전자화함으로써 행정기관 등의 상호 간의 행정업무 및 국민에 대한 행정업무를 효율적으로 수행하는 정부를 말한다.
2. "행정전자서명"이란 전자문서를 작성한 행정기관 등 또는 그 기관에서 직접 업무를 담당하는 사람의 신원과 전자문서의 변경 여부를 확인할 수 있는 정보를 말한다.

제12조(행정정보의 공동이용) ① 행정기관등은 수집·보유하고 있는 행정정보를 필요로 하는 다른 행정기관등과 공동으로 이용하여야 하며, 다른 행정기관등으로부터 신뢰할 수 있는 행정정보를 제공받을 수 있는 경우에는 같은 내용의 정보를 따로 수집하여서는 아니 된다.

제56조(개인정보 보호) 행정기관등은 전자정부의 구현·운영을 통하여 수집·이용·제공되는 개인정보의 보호를 위한 대책을 마련하여야 한다."""

    def _sample_software_law(self) -> str:
        return """제1조(목적) 이 법은 소프트웨어산업의 진흥에 필요한 사항을 정함으로써 소프트웨어산업 발전의 기반을 조성하고 소프트웨어산업의 경쟁력을 강화하여 국민생활의 향상과 국민경제의 건전한 발전에 이바지함을 목적으로 한다.

제2조(정의) 이 법에서 사용하는 용어의 뜻은 다음과 같다.
1. "소프트웨어"란 컴퓨터, 통신, 자동화 등의 장비와 그 주변장치에 대하여 명령·제어·입력·처리·저장·출력·상호작용이 가능하게 하는 지시·명령의 집합과 이를 작성하기 위하여 사용된 기술서나 그 밖의 관련 자료를 말한다.
2. "소프트웨어산업"이란 소프트웨어의 개발, 제작, 생산, 유통 등과 이에 관련된 서비스 및 정보시스템의 구축·운영 등과 관련된 산업을 말한다.

제10조(소프트웨어진흥시설의 지정 등) ① 과학기술정보통신부장관은 소프트웨어산업의 진흥을 위하여 소프트웨어 관련 연구개발 및 인력양성을 위한 시설을 소프트웨어진흥시설로 지정할 수 있다.

제20조(소프트웨어사업의 대가 기준) ① 국가기관등이 소프트웨어사업을 추진할 때에는 소프트웨어산업의 건전한 발전을 위하여 정당한 대가를 지급하여야 한다.
② 대가 기준의 세부사항은 과학기술정보통신부장관이 정하여 고시한다."""

    def _sample_smart_info_law(self) -> str:
        return """제1조(목적) 이 법은 지능정보화 관련 정책의 수립·시행 등에 관한 사항을 규정함으로써 지능정보사회의 발전에 이바지하고 국민의 삶의 질을 높이는 것을 목적으로 한다.

제2조(정의) 이 법에서 사용하는 용어의 뜻은 다음과 같다.
1. "지능정보기술"이란 인간의 고차원적 정보처리와 같은 기능을 가진 기술로서 전자적 방법으로 학습·추론·판단 등을 구현하는 기술, 데이터를 전자적 방법으로 수집·분석·가공 등 처리하는 기술, 물건 상호 간 또는 사람과 물건 사이에 데이터를 처리하거나 물리적 행동을 하는 기술을 말한다.
2. "지능정보서비스"란 지능정보기술을 활용한 서비스를 말한다.

제48조(지능정보서비스 과의존 관련 교육) 과학기술정보통신부장관은 지능정보서비스 과의존의 예방 및 해소를 위하여 교육을 실시할 수 있다.

제60조(이용자의 권익 보호) ① 지능정보서비스 제공자는 이용자가 지능정보서비스를 이용함에 있어 불합리한 차별을 받지 않도록 하여야 한다.
② 지능정보서비스 제공자는 이용자의 권리침해를 예방하기 위한 조치를 마련하여야 한다."""

    def _sample_digital_transform_law(self) -> str:
        return """제1조(목적) 이 법은 산업의 디지털 전환을 촉진하여 산업의 경쟁력을 강화하고 국민경제의 발전에 이바지함을 목적으로 한다.

제2조(정의) 이 법에서 사용하는 용어의 뜻은 다음과 같다.
1. "디지털 전환"이란 디지털 기술을 산업에 적용하여 전통적인 산업 구조를 혁신적으로 변화시키는 것을 말한다.
2. "디지털 기술"이란 인공지능, 사물인터넷, 클라우드컴퓨팅, 빅데이터, 5세대 이동통신 등 산업의 디지털 전환을 위하여 필요한 기술을 말한다.
3. "스마트공장"이란 디지털 기술을 적용하여 생산성, 품질, 고객만족도 등을 향상시키는 지능형 공장을 말한다.

제7조(산업 디지털 전환 기본계획) ① 산업통상자원부장관은 산업의 디지털 전환 촉진을 위하여 5년마다 산업 디지털 전환 기본계획을 수립하여야 한다.
② 기본계획에는 다음 각 호의 사항이 포함되어야 한다.
1. 산업 디지털 전환의 기본방향
2. 디지털 기술 연구개발 지원에 관한 사항
3. 스마트공장 보급·확산에 관한 사항
4. 산업 디지털 전환 전문인력 양성에 관한 사항
5. 중소기업의 디지털 전환 지원에 관한 사항

제15조(디지털 전환 데이터의 활용) ① 기업은 산업 활동에서 생성되는 데이터를 디지털 전환에 활용할 수 있다.
② 정부는 산업 데이터의 수집·분석·활용을 위한 기반을 구축하여야 한다."""

    def _sample_generic_law(self, title: str) -> str:
        return f"""제1조(목적) 이 법은 {title}에 관한 사항을 규정함으로써 관련 산업의 발전과 국민의 삶의 질 향상에 이바지함을 목적으로 한다.

제2조(정의) 이 법에서 사용하는 용어의 뜻은 관계 법령에서 정하는 바에 따른다.

제3조(국가 등의 책무) ① 국가와 지방자치단체는 {title}의 이행을 위한 시책을 수립·시행하여야 한다.
② 관련 사업자는 이 법의 규정을 준수하고 국가 시책에 협력하여야 한다."""

    def _parse_law_row(self, row) -> dict | None:
        """HTML 행에서 법령 정보 파싱"""
        try:
            link_tag = row.select_one("a")
            if not link_tag:
                return None

            title = link_tag.get_text(strip=True)
            href = link_tag.get("href", "")

            # lsId 추출
            law_id = ""
            if "lsId=" in href:
                law_id = href.split("lsId=")[1].split("&")[0]
            elif "lsiSeq=" in href:
                law_id = href.split("lsiSeq=")[1].split("&")[0]

            # 날짜 정보 추출
            date_cells = row.select("td")
            pub_date = ""
            if len(date_cells) >= 3:
                pub_date = date_cells[2].get_text(strip=True)

            return {
                "id": law_id or f"LAW_{hash(title) % 100000:05d}",
                "title": title,
                "url": f"{self.base_url}{href}" if href.startswith("/") else href,
                "pub_date": pub_date,
                "crawled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        except Exception:
            return None

    def _get_laws_from_api(self, limit: int) -> list[dict]:
        """국가법령정보 Open API를 통한 법령 목록 수집 (대체 방법)"""
        laws = []
        try:
            # 공공데이터 포털의 법령 API (인증키 불필요한 기본 조회)
            api_url = f"{self.base_url}/DRF/lawSearch.do"
            params = {
                "OC": "test",
                "target": "law",
                "type": "JSON",
                "display": str(limit),
                "sort": "date",
            }
            print(f"[크롤링] Open API로 대체 수집 시도: {api_url}")

            response = self.session.get(api_url, params=params, timeout=30)
            response.raise_for_status()

            data = response.json()
            law_list = data.get("LawSearch", {}).get("law", [])
            if isinstance(law_list, dict):
                law_list = [law_list]

            for item in law_list[:limit]:
                laws.append({
                    "id": str(item.get("법령일련번호", item.get("MST", ""))),
                    "title": item.get("법령명한글", item.get("법령명", "")),
                    "url": f"{self.base_url}/LSW/lsInfoP.do?lsiSeq={item.get('법령일련번호', '')}",
                    "pub_date": item.get("공포일자", item.get("시행일자", "")),
                    "crawled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                })

            print(f"[크롤링] API에서 {len(laws)}개 법령 수집 완료")

        except Exception as e:
            print(f"[크롤링 오류] API 수집도 실패: {e}")

        return laws

    def get_law_detail(self, law_id: str) -> dict | None:
        """특정 법령의 상세 내용 가져오기"""
        try:
            print(f"[크롤링] 법령 상세 수집: {law_id}")

            # 법령 상세 페이지
            url = f"{self.base_url}/LSW/lsInfoP.do?lsiSeq={law_id}"
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            response.encoding = "utf-8"

            soup = BeautifulSoup(response.text, "html.parser")

            # 법령 본문 추출
            content_area = soup.select_one("#conScroll, .lawcon, #lawService")
            content_text = ""
            if content_area:
                content_text = content_area.get_text(separator="\n", strip=True)
            else:
                # 전체 body에서 주요 콘텐츠 추출
                body = soup.select_one("body")
                if body:
                    # 스크립트, 스타일 제거
                    for tag in body.select("script, style, nav, header, footer"):
                        tag.decompose()
                    content_text = body.get_text(separator="\n", strip=True)

            # 제목 추출
            title = ""
            title_tag = soup.select_one("h2, .tit, #lsNm")
            if title_tag:
                title = title_tag.get_text(strip=True)

            # 마크다운 형태로 변환
            markdown_content = self._convert_to_markdown(title, content_text, law_id)

            return {
                "id": law_id,
                "title": title,
                "content": content_text[:50000],  # 최대 50KB
                "markdown": markdown_content,
                "url": url,
                "crawled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

        except Exception as e:
            print(f"[크롤링 오류] 법령 상세 수집 실패 ({law_id}): {e}")
            return None

    def _convert_to_markdown(self, title: str, content: str, law_id: str) -> str:
        """크롤링된 텍스트를 Markdown으로 변환"""
        lines = []
        lines.append(f"# {title}")
        lines.append("")
        lines.append(f"> 법령 ID: {law_id}")
        lines.append(f"> 크롤링 일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        for line in content.split("\n"):
            line = line.strip()
            if not line:
                continue
            # 조문 패턴: 제1조, 제2조 등
            if re.match(r"^제\d+조", line):
                lines.append(f"## {line}")
            # 항 패턴: ①, ②, ③ 등
            elif re.match(r"^[①②③④⑤⑥⑦⑧⑨⑩]", line):
                lines.append(f"- {line}")
            # 호 패턴: 1., 2., 3. 등
            elif re.match(r"^\d+\.", line):
                lines.append(f"  - {line}")
            else:
                lines.append(line)
            lines.append("")

        return "\n".join(lines)

    def save_to_file(self, data: dict | list, filepath: str) -> None:
        """데이터를 JSON 파일로 저장"""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[저장] {filepath}")

    def save_markdown(self, content: str, filepath: str) -> None:
        """마크다운 파일로 저장"""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[저장] {filepath}")


if __name__ == "__main__":
    crawler = LawCrawler()

    # 최근 법령 목록 수집
    laws = crawler.get_recent_laws(limit=5)
    if laws:
        today = datetime.now().strftime("%Y-%m-%d")
        crawler.save_to_file(laws, f"data/raw/{today}/law_list.json")

        # 첫 번째 법령 상세 수집
        detail = crawler.get_law_detail(laws[0]["id"])
        if detail:
            crawler.save_to_file(detail, f"data/raw/{today}/law_{laws[0]['id']}.json")
            if detail.get("markdown"):
                crawler.save_markdown(
                    detail["markdown"],
                    f"data/raw/{today}/law_{laws[0]['id']}.md",
                )
