#!/usr/bin/env bash
# ==============================================================================
# 멀티모달 데이터셋 업로드 스크립트
# ZIP 파일(과학기술/사회과학)에서 PDF/PPTX를 추출하여 Azure Blob Storage에 업로드
# ==============================================================================
set -euo pipefail

# ── 기본 설정 ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="${PROJECT_ROOT}/.env"

# ZIP 파일 경로
ZIP_ST="/mnt/codes/TS_과학기술(ST).zip"
ZIP_SS="/mnt/codes/TS_사회과학(SS).zip"

# Azure Blob Storage 설정
CONTAINER_NAME="raw-documents"
STORAGE_ACCOUNT_NAME=""

# 임시 디렉토리
TEMP_DIR=""
DRY_RUN=false

# ── 도움말 ──
usage() {
    cat <<EOF
사용법: $(basename "$0") [옵션]

멀티모달 데이터셋(PDF/PPTX)을 Azure Blob Storage에 업로드합니다.

옵션:
  -s, --storage-account NAME   Storage Account 이름 (미지정 시 .env에서 읽음)
  -c, --container NAME         Blob 컨테이너 이름 (기본: raw-documents)
  --st-zip PATH                과학기술 ZIP 경로 (기본: $ZIP_ST)
  --ss-zip PATH                사회과학 ZIP 경로 (기본: $ZIP_SS)
  --dry-run                    실제 업로드 없이 계획만 출력
  -h, --help                   도움말 출력

예시:
  $(basename "$0")
  $(basename "$0") --storage-account mystorageaccount
  $(basename "$0") --dry-run
EOF
    exit 0
}

# ── 인자 파싱 ──
while [[ $# -gt 0 ]]; do
    case "$1" in
        -s|--storage-account) STORAGE_ACCOUNT_NAME="$2"; shift 2 ;;
        -c|--container) CONTAINER_NAME="$2"; shift 2 ;;
        --st-zip) ZIP_ST="$2"; shift 2 ;;
        --ss-zip) ZIP_SS="$2"; shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        -h|--help) usage ;;
        *) echo "ERROR: 알 수 없는 옵션: $1"; usage ;;
    esac
done

# ── .env에서 스토리지 계정 이름 읽기 ──
if [[ -z "$STORAGE_ACCOUNT_NAME" ]]; then
    if [[ -f "$ENV_FILE" ]]; then
        STORAGE_ACCOUNT_NAME=$(grep -E '^AZURE_STORAGE_ACCOUNT_NAME=' "$ENV_FILE" | cut -d'=' -f2- | tr -d '"' | tr -d "'")
    fi
    if [[ -z "$STORAGE_ACCOUNT_NAME" ]]; then
        echo "ERROR: Storage Account 이름이 필요합니다."
        echo "  .env 파일에 AZURE_STORAGE_ACCOUNT_NAME을 설정하거나 --storage-account 옵션을 사용하세요."
        exit 1
    fi
fi

# ── ZIP 파일 존재 확인 ──
check_zip_files() {
    local missing=0
    for zip_path in "$ZIP_ST" "$ZIP_SS"; do
        if [[ ! -f "$zip_path" ]]; then
            echo "WARN: ZIP 파일을 찾을 수 없습니다: $zip_path"
            missing=$((missing + 1))
        fi
    done
    if [[ $missing -eq 2 ]]; then
        echo "ERROR: 업로드할 ZIP 파일이 없습니다."
        exit 1
    fi
}

# ── 도구 확인 ──
check_prerequisites() {
    if ! command -v az &>/dev/null; then
        echo "ERROR: Azure CLI (az)가 설치되어 있지 않습니다."
        exit 1
    fi

    # azcopy 사용 가능 여부 확인
    if command -v azcopy &>/dev/null; then
        echo "INFO: azcopy 사용 가능 — 대용량 전송에 활용합니다."
        USE_AZCOPY=true
    else
        echo "INFO: azcopy 미설치 — az storage blob upload-batch로 대체합니다."
        USE_AZCOPY=false
    fi

    # Azure 로그인 상태 확인
    if ! az account show &>/dev/null 2>&1; then
        echo "ERROR: Azure 로그인이 필요합니다. 'az login'을 먼저 실행하세요."
        exit 1
    fi
}

# ── 정리 함수 ──
cleanup() {
    if [[ -n "$TEMP_DIR" && -d "$TEMP_DIR" ]]; then
        echo ""
        echo "── 임시 파일 정리 ──"
        rm -rf "$TEMP_DIR"
        echo "OK: 임시 디렉토리 삭제 완료"
    fi
}
trap cleanup EXIT

# ── ZIP에서 PDF/PPTX만 추출 ──
# NOTE: 손상된 ZIP(다운로드 미완료 등)도 7z로 추출 가능한 파일만 처리
extract_files() {
    local zip_path="$1"
    local category="$2"  # ST 또는 SS
    local extract_dir="$TEMP_DIR/$category"

    if [[ ! -f "$zip_path" ]]; then
        echo "SKIP: $zip_path 없음"
        return
    fi

    echo ""
    echo "── ZIP 추출: $category ──"
    echo "  소스: $zip_path"

    mkdir -p "$extract_dir/pdf" "$extract_dir/pptx"

    # 7z 사용 가능 시 7z로 추출 (손상된 ZIP 지원), 아니면 unzip 사용
    if command -v 7z &>/dev/null; then
        echo "  7z로 PDF/PPTX 추출 중 (손상 ZIP도 지원)..."
        local staging_dir="$TEMP_DIR/_staging_${category}"
        mkdir -p "$staging_dir"

        # 7z로 추출 — 먼저 -ir 패턴 시도, 실패 시 전체 추출 후 필터링
        7z x -o"$staging_dir" -y \
            -ir'!*.pdf' -ir'!*.PDF' -ir'!*.pptx' -ir'!*.PPTX' \
            "$zip_path" 2>/dev/null || true

        # -ir 패턴으로 0개면 전체 추출 후 필터 (손상 ZIP의 경우)
        local ir_count
        ir_count=$(find "$staging_dir" -type f 2>/dev/null | wc -l)
        if [[ "$ir_count" -eq 0 ]]; then
            echo "  -ir 필터 실패 — 전체 추출 후 필터링 시도..."
            7z x -o"$staging_dir" -y "$zip_path" 2>/dev/null || true
        fi

        # 추출된 파일을 pdf/pptx 디렉토리로 분류 (flat)
        find "$staging_dir" -iname '*.pdf' -size +0c -exec mv {} "$extract_dir/pdf/" \; 2>/dev/null || true
        find "$staging_dir" -iname '*.pptx' -size +0c -exec mv {} "$extract_dir/pptx/" \; 2>/dev/null || true

        # 스테이징 정리
        rm -rf "$staging_dir"
    else
        # unzip 사용 (정상 ZIP만 처리 가능)
        echo "  PDF/PPTX 파일 목록 조회 중..."
        local file_list
        file_list=$(unzip -l "$zip_path" 2>/dev/null | grep -iE '\.(pdf|pptx)$' | awk '{print $NF}' || true)

        if [[ -z "$file_list" ]]; then
            echo "  WARN: PDF/PPTX 파일이 없습니다."
            return
        fi

        local total_files
        total_files=$(echo "$file_list" | wc -l)
        echo "  대상 파일 수: $total_files"

        echo "  추출 중..."
        echo "$file_list" | while IFS= read -r file; do
            local ext="${file##*.}"
            ext=$(echo "$ext" | tr '[:upper:]' '[:lower:]')

            if [[ "$ext" == "pdf" ]]; then
                unzip -o -j "$zip_path" "$file" -d "$extract_dir/pdf/" 2>/dev/null || true
            elif [[ "$ext" == "pptx" ]]; then
                unzip -o -j "$zip_path" "$file" -d "$extract_dir/pptx/" 2>/dev/null || true
            fi
        done
    fi

    local pdf_count pptx_count
    pdf_count=$(find "$extract_dir/pdf" -type f \( -iname '*.pdf' \) 2>/dev/null | wc -l)
    pptx_count=$(find "$extract_dir/pptx" -type f \( -iname '*.pptx' \) 2>/dev/null | wc -l)
    echo "  추출 완료: PDF=$pdf_count, PPTX=$pptx_count"
}

# ── Blob Storage에 업로드 ──
upload_to_blob() {
    local source_dir="$1"
    local blob_prefix="$2"
    local desc="$3"

    if [[ ! -d "$source_dir" ]] || [[ -z "$(ls -A "$source_dir" 2>/dev/null)" ]]; then
        echo "  SKIP: $desc — 업로드할 파일 없음"
        return
    fi

    local file_count
    file_count=$(find "$source_dir" -type f | wc -l)
    echo "  업로드: $desc ($file_count 파일) → $blob_prefix"

    if $DRY_RUN; then
        echo "  [DRY-RUN] 업로드 생략"
        return
    fi

    if $USE_AZCOPY; then
        # azcopy — Azure CLI 인증 사용
        local blob_url="https://${STORAGE_ACCOUNT_NAME}.blob.core.windows.net/${CONTAINER_NAME}/${blob_prefix}"
        AZCOPY_AUTO_LOGIN_TYPE=AZCLI azcopy copy \
            "${source_dir}/*" \
            "$blob_url" \
            --recursive=false \
            --log-level=ERROR \
            --put-md5 \
            2>&1 | tail -5
    else
        # az storage blob upload-batch — Azure AD 인증
        az storage blob upload-batch \
            --account-name "$STORAGE_ACCOUNT_NAME" \
            --destination "$CONTAINER_NAME" \
            --destination-path "$blob_prefix" \
            --source "$source_dir" \
            --auth-mode login \
            --overwrite true \
            --output none \
            --only-show-errors
    fi

    echo "  OK: $desc 업로드 완료"
}

# ── 메인 실행 ──
main() {
    echo "=============================================="
    echo " 멀티모달 데이터셋 업로드"
    echo "=============================================="
    echo "Storage Account : $STORAGE_ACCOUNT_NAME"
    echo "Container       : $CONTAINER_NAME"
    echo "Dry Run         : $DRY_RUN"
    echo ""

    check_zip_files
    check_prerequisites

    # 임시 디렉토리 생성
    TEMP_DIR=$(mktemp -d -t multimodal-upload-XXXXXX)
    echo "임시 디렉토리: $TEMP_DIR"

    # ── ZIP 추출 ──
    extract_files "$ZIP_ST" "ST"
    extract_files "$ZIP_SS" "SS"

    # ── 추출 결과 요약 ──
    echo ""
    echo "── 추출 결과 요약 ──"
    local total_pdf=0 total_pptx=0
    for cat in ST SS; do
        local dir="$TEMP_DIR/$cat"
        if [[ -d "$dir" ]]; then
            local pc=$(find "$dir/pdf" -type f 2>/dev/null | wc -l)
            local xc=$(find "$dir/pptx" -type f 2>/dev/null | wc -l)
            echo "  $cat: PDF=$pc, PPTX=$xc"
            total_pdf=$((total_pdf + pc))
            total_pptx=$((total_pptx + xc))
        fi
    done
    echo "  합계: PDF=$total_pdf, PPTX=$total_pptx"

    # ── 업로드 ──
    echo ""
    echo "── 업로드 시작 ──"

    for cat in ST SS; do
        local dir="$TEMP_DIR/$cat"
        if [[ -d "$dir" ]]; then
            upload_to_blob "$dir/pdf"  "raw/pdf/$cat"  "$cat PDF"
            upload_to_blob "$dir/pptx" "raw/pptx/$cat" "$cat PPTX"
        fi
    done

    # ── 최종 요약 ──
    echo ""
    echo "=============================================="
    echo " 업로드 완료 요약"
    echo "=============================================="
    echo "  Storage : ${STORAGE_ACCOUNT_NAME}"
    echo "  Container: ${CONTAINER_NAME}"
    echo "  PDF  → raw/pdf/ST/, raw/pdf/SS/"
    echo "  PPTX → raw/pptx/ST/, raw/pptx/SS/"
    if $DRY_RUN; then
        echo "  ⚠ DRY-RUN 모드: 실제 업로드는 수행되지 않았습니다."
    fi
    echo "=============================================="
}

main
