# Common Error Patterns & Fix Locations

이 워크스페이스에서 자주 발생하는 에러 패턴과 수정 위치 참조.

## 1. Azure SDK / API Errors

### ResourceNotFoundError (404)
```
azure.core.exceptions.ResourceNotFoundError: (ResourceNotFound)
```
- **원인**: 인프라가 아직 배포되지 않았거나, 리소스 이름이 .env와 불일치
- **수정 위치**: `infra/` Bicep 파일 또는 `.env`
- **확인**: `az resource list --resource-group $AZURE_RESOURCE_GROUP`

### AuthenticationError / CredentialUnavailableError
```
azure.identity._exceptions.CredentialUnavailableError
```
- **원인**: Azure CLI 로그인 만료 또는 tenant_id 불일치
- **수정**: `az login --tenant <TENANT_ID>` 실행
- **영구 수정**: 노트북에서 credential 생성 코드 확인

### HttpResponseError (403 Forbidden)
```
azure.core.exceptions.HttpResponseError: (AuthorizationFailed)
```
- **원인**: RBAC 역할 할당 누락
- **수정 위치**: `infra/` Bicep의 role assignment 모듈

## 2. Import / Module Errors

### ModuleNotFoundError (src 모듈)
```
ModuleNotFoundError: No module named 'src'
```
- **원인**: `sys.path.insert(0, os.path.abspath('..'))` 누락 또는 커널 CWD 문제
- **수정 위치**: 노트북 초기 셀의 sys.path 설정

### ModuleNotFoundError (외부 패키지)
```
ModuleNotFoundError: No module named 'azure.search.documents'
```
- **원인**: 패키지 미설치
- **수정 위치**: `requirements.txt`에 추가 후 `pip install -r requirements.txt`

### ImportError (API 변경)
```
ImportError: cannot import name 'X' from 'src.search.legal_indexes'
```
- **원인**: src/ 모듈의 클래스/함수 이름 변경
- **수정 위치**: `src/` 모듈 (이름 복구) 또는 노트북 import 문 (새 이름 반영)
- **판단 기준**: 여러 노트북에서 같은 import를 쓰면 → src/ 수정. 하나만이면 → 노트북 수정

## 3. Environment / Config Errors

### KeyError (환경변수)
```
KeyError: 'AZURE_SEARCH_SERVICE_ENDPOINT'
```
- **원인**: `.env` 파일에 키 누락 또는 `load_dotenv()` 경로 오류
- **수정 위치**: `.env` (키 추가) 또는 `sample.env`와 비교

### FileNotFoundError (.env)
```
FileNotFoundError: [Errno 2] No such file or directory: '../.env'
```
- **수정**: `cp sample.env .env` 후 값 설정

## 4. Bicep / Infrastructure Errors

### Deployment Failed
```
DeploymentFailed: At least one resource deployment operation failed
```
- **수정 위치**: `infra/{region}/main.bicep` 또는 `infra/{region}/modules/`
- **확인**: Azure Portal에서 배포 에러 상세 확인

### Parameter Validation Error
```
InvalidTemplate: The template parameter 'X' is not valid
```
- **수정 위치**: `infra/{region}/parameters/` JSON 파일

## 5. Search Index Errors

### Index Schema Mismatch
```
azure.core.exceptions.HttpResponseError: The request is invalid.
```
- **원인**: 인덱스 스키마 정의와 실제 데이터 구조 불일치
- **수정 위치**: `src/search/legal_indexes.py` 또는 `src/search/multimodal_index.py`

### Indexer Execution Error
```
Indexer 'X' execution failed: ...
```
- **원인**: skillset 정의 또는 데이터 소스 연결 문제
- **수정 위치**: `scripts/setup_ai_search_pipeline.py` 또는 `scripts/setup_ai_search_multimodal_pipeline.py`
