import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from copy import deepcopy
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ai_extraction import extract_tasks_by_rules, extract_tasks_via_openrouter  # noqa: E402


TEXT_OPENROUTER = "text_openrouter"
TEXT_RULES = "text_rules"
WHISPER_OPENROUTER = "whisper_openrouter"
WHISPER_RULES = "whisper_rules"
ALL_PIPELINES = (
    TEXT_OPENROUTER,
    TEXT_RULES,
    WHISPER_OPENROUTER,
    WHISPER_RULES,
)

_WHISPER_MODEL = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark task extraction quality for OpenRouter and Whisper-based flows.",
    )
    parser.add_argument(
        "--cases",
        default=str(Path(__file__).with_name("task_extraction_benchmark_cases.100.json")),
        help="Path to benchmark JSON cases.",
    )
    parser.add_argument(
        "--pipelines",
        default=",".join(ALL_PIPELINES),
        help=f"Comma-separated pipelines: {', '.join(ALL_PIPELINES)}",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional path to save full JSON report.",
    )
    parser.add_argument(
        "--title-threshold",
        type=float,
        default=0.72,
        help="Minimum normalized title similarity to treat tasks as matched.",
    )
    parser.add_argument(
        "--fail-missing-audio",
        action="store_true",
        help="Fail instead of skipping when an audio case file does not exist.",
    )
    return parser.parse_args()


def load_cases(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        cases = raw.get("cases")
    else:
        cases = raw
    if not isinstance(cases, list):
        raise ValueError("Cases file must contain a JSON array or an object with 'cases'.")
    normalized: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict):
            raise ValueError(f"Case #{index} is not an object.")
        item = deepcopy(case)
        item.setdefault("id", f"case_{index:03d}")
        item.setdefault("category", "uncategorized")
        item.setdefault("project_title", "Новый проект")
        item.setdefault("input_text", "")
        item.setdefault("context_text", "")
        item.setdefault("expected_tasks", [])
        normalized.append(item)
    return normalized


def normalize_text(value: Any) -> str:
    text = str(value or "").lower().strip()
    cleaned = []
    for char in text:
        if char.isalnum() or char.isspace():
            cleaned.append(char)
        else:
            cleaned.append(" ")
    return " ".join("".join(cleaned).split())


def title_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, normalize_text(left), normalize_text(right)).ratio()


def tokenize(value: str) -> list[str]:
    return [token for token in normalize_text(value).split() if token]


def levenshtein_distance(left: list[str], right: list[str]) -> int:
    if not left:
        return len(right)
    if not right:
        return len(left)
    prev = list(range(len(right) + 1))
    for i, lval in enumerate(left, start=1):
        curr = [i]
        for j, rval in enumerate(right, start=1):
            cost = 0 if lval == rval else 1
            curr.append(
                min(
                    prev[j] + 1,
                    curr[j - 1] + 1,
                    prev[j - 1] + cost,
                )
            )
        prev = curr
    return prev[-1]


def calc_wer(expected_text: str, actual_text: str) -> float | None:
    expected_tokens = tokenize(expected_text)
    actual_tokens = tokenize(actual_text)
    if not expected_tokens:
        return None
    return levenshtein_distance(expected_tokens, actual_tokens) / len(expected_tokens)


def calc_cer(expected_text: str, actual_text: str) -> float | None:
    expected_chars = list(normalize_text(expected_text).replace(" ", ""))
    actual_chars = list(normalize_text(actual_text).replace(" ", ""))
    if not expected_chars:
        return None
    return levenshtein_distance(expected_chars, actual_chars) / len(expected_chars)


def clamp_score(value: float) -> float:
    return max(0.0, min(1.0, value))


def match_tasks(
    expected_tasks: list[dict[str, Any]],
    predicted_tasks: list[dict[str, Any]],
    title_threshold: float,
) -> dict[str, Any]:
    expected_pool = list(enumerate(expected_tasks))
    predicted_pool = list(enumerate(predicted_tasks))
    candidates: list[tuple[float, int, int]] = []
    for predicted_index, predicted in predicted_pool:
        for expected_index, expected in expected_pool:
            similarity = title_similarity(
                str(predicted.get("title") or ""),
                str(expected.get("title") or ""),
            )
            if similarity >= title_threshold:
                candidates.append((similarity, expected_index, predicted_index))
    candidates.sort(reverse=True)

    used_expected: set[int] = set()
    used_predicted: set[int] = set()
    matches: list[dict[str, Any]] = []
    for similarity, expected_index, predicted_index in candidates:
        if expected_index in used_expected or predicted_index in used_predicted:
            continue
        used_expected.add(expected_index)
        used_predicted.add(predicted_index)
        expected = expected_tasks[expected_index]
        predicted = predicted_tasks[predicted_index]
        expected_status = str(expected.get("status") or "NEW").upper()
        predicted_status = str(predicted.get("status") or "NEW").upper()
        expected_hours = expected.get("execution_hours")
        predicted_hours = predicted.get("execution_hours")
        matches.append(
            {
                "expected_index": expected_index,
                "predicted_index": predicted_index,
                "title_similarity": round(similarity, 4),
                "status_match": expected_status == predicted_status,
                "hours_match": expected_hours == predicted_hours if expected_hours is not None else True,
                "expected_title": expected.get("title"),
                "predicted_title": predicted.get("title"),
            }
        )

    false_negatives = [
        expected_tasks[index]
        for index in range(len(expected_tasks))
        if index not in used_expected
    ]
    false_positives = [
        predicted_tasks[index]
        for index in range(len(predicted_tasks))
        if index not in used_predicted
    ]
    matched_count = len(matches)
    expected_count = len(expected_tasks)
    predicted_count = len(predicted_tasks)
    if expected_count == 0 and predicted_count == 0:
        precision = 1.0
        recall = 1.0
        f1 = 1.0
    else:
        precision = matched_count / predicted_count if predicted_count else 0.0
        recall = matched_count / expected_count if expected_count else 1.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    status_accuracy = (
        sum(1 for item in matches if item["status_match"]) / matched_count
        if matched_count
        else (1.0 if expected_count == predicted_count == 0 else 0.0)
    )
    hours_accuracy = (
        sum(1 for item in matches if item["hours_match"]) / matched_count
        if matched_count
        else (1.0 if expected_count == predicted_count == 0 else 0.0)
    )
    avg_title_similarity = (
        sum(item["title_similarity"] for item in matches) / matched_count
        if matched_count
        else (1.0 if expected_count == predicted_count == 0 else 0.0)
    )
    strict_match = (
        expected_count == predicted_count
        and matched_count == expected_count
        and all(item["status_match"] for item in matches)
        and all(item["hours_match"] for item in matches)
    )
    return {
        "matched_count": matched_count,
        "expected_count": expected_count,
        "predicted_count": predicted_count,
        "precision": round(clamp_score(precision), 4),
        "recall": round(clamp_score(recall), 4),
        "f1": round(clamp_score(f1), 4),
        "status_accuracy": round(clamp_score(status_accuracy), 4),
        "hours_accuracy": round(clamp_score(hours_accuracy), 4),
        "avg_title_similarity": round(clamp_score(avg_title_similarity), 4),
        "strict_match": strict_match,
        "matches": matches,
        "false_negatives": false_negatives,
        "false_positives": false_positives,
    }


def run_text_openrouter(case: dict[str, Any]) -> list[dict[str, Any]]:
    return extract_tasks_via_openrouter(case["input_text"], case["project_title"])


def run_text_rules(case: dict[str, Any]) -> list[dict[str, Any]]:
    return extract_tasks_by_rules(case["input_text"])


def get_whisper_model():
    global _WHISPER_MODEL
    if _WHISPER_MODEL is None:
        from faster_whisper import WhisperModel

        model_name = os.getenv("WHISPER_MODEL", "base").strip() or "base"
        device = os.getenv("WHISPER_DEVICE", "cpu").strip() or "cpu"
        compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "int8").strip() or "int8"
        download_root = os.getenv("WHISPER_CACHE_DIR", "").strip() or None
        _WHISPER_MODEL = WhisperModel(
            model_name,
            device=device,
            compute_type=compute_type,
            download_root=download_root,
        )
    return _WHISPER_MODEL


def transcribe_media_bytes(content: bytes, suffix: str) -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_file.write(content)
        temp_path = temp_file.name
    try:
        model = get_whisper_model()
        language = os.getenv("WHISPER_LANGUAGE", "ru").strip() or None
        task = os.getenv("WHISPER_TASK", "transcribe").strip() or "transcribe"
        initial_prompt = os.getenv("WHISPER_INITIAL_PROMPT", "").strip() or None
        beam_size_raw = os.getenv("WHISPER_BEAM_SIZE", "5").strip() or "5"
        best_of_raw = os.getenv("WHISPER_BEST_OF", "5").strip() or "5"
        temperature_raw = os.getenv("WHISPER_TEMPERATURE", "0").strip() or "0"
        try:
            beam_size = max(1, int(beam_size_raw))
        except ValueError:
            beam_size = 5
        try:
            best_of = max(1, int(best_of_raw))
        except ValueError:
            best_of = 5
        try:
            temperature = float(temperature_raw)
        except ValueError:
            temperature = 0.0
        for vad_filter in (True, False):
            segments, _info = model.transcribe(
                temp_path,
                language=language,
                task=task,
                vad_filter=vad_filter,
                beam_size=beam_size,
                best_of=best_of,
                temperature=temperature,
                condition_on_previous_text=False,
                initial_prompt=initial_prompt,
            )
            chunks = []
            for segment in segments:
                text = (segment.text or "").strip()
                if text:
                    chunks.append(text)
            transcript = " ".join(chunks).strip()
            if transcript:
                return transcript
        return ""
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass


def resolve_audio_path(case: dict[str, Any], cases_path: Path) -> Path:
    raw_path = str(case.get("audio_path") or "").strip()
    if not raw_path:
        raise FileNotFoundError("audio_path is empty")
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate
    return (cases_path.parent / candidate).resolve()


def build_audio_source_text(case: dict[str, Any], transcript: str) -> str:
    parts = []
    context_text = str(case.get("context_text") or "").strip()
    if context_text:
        parts.append(context_text)
    if transcript.strip():
        parts.append("Текст из аудио/видео:\n" + transcript.strip())
    return "\n\n".join(parts).strip()


def transcribe_case_audio(case: dict[str, Any], cases_path: Path) -> tuple[str, str]:
    audio_path = resolve_audio_path(case, cases_path)
    content = audio_path.read_bytes()
    transcript = transcribe_media_bytes(content, audio_path.suffix or ".mp3")
    return str(audio_path), transcript


def safe_float_mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(statistics.fmean(values), 4)


def summarize_pipeline(results: list[dict[str, Any]]) -> dict[str, Any]:
    executed = [item for item in results if item["status"] == "ok"]
    failed = [item for item in results if item["status"] == "error"]
    skipped = [item for item in results if item["status"] == "skipped"]
    categories = sorted({item["category"] for item in results})
    summary: dict[str, Any] = {
        "total_cases": len(results),
        "executed_cases": len(executed),
        "failed_cases": len(failed),
        "skipped_cases": len(skipped),
        "avg_latency_sec": safe_float_mean([item["latency_sec"] for item in executed]),
        "strict_match_rate": safe_float_mean([1.0 if item["task_metrics"]["strict_match"] else 0.0 for item in executed]),
        "avg_precision": safe_float_mean([item["task_metrics"]["precision"] for item in executed]),
        "avg_recall": safe_float_mean([item["task_metrics"]["recall"] for item in executed]),
        "avg_f1": safe_float_mean([item["task_metrics"]["f1"] for item in executed]),
        "avg_title_similarity": safe_float_mean([item["task_metrics"]["avg_title_similarity"] for item in executed]),
        "avg_status_accuracy": safe_float_mean([item["task_metrics"]["status_accuracy"] for item in executed]),
        "avg_hours_accuracy": safe_float_mean([item["task_metrics"]["hours_accuracy"] for item in executed]),
        "avg_wer": safe_float_mean(
            [
                item["transcript_metrics"]["wer"]
                for item in executed
                if item.get("transcript_metrics") and item["transcript_metrics"].get("wer") is not None
            ]
        ),
        "avg_cer": safe_float_mean(
            [
                item["transcript_metrics"]["cer"]
                for item in executed
                if item.get("transcript_metrics") and item["transcript_metrics"].get("cer") is not None
            ]
        ),
        "by_category": {},
    }
    for category in categories:
        category_items = [item for item in executed if item["category"] == category]
        summary["by_category"][category] = {
            "executed_cases": len(category_items),
            "avg_f1": safe_float_mean([item["task_metrics"]["f1"] for item in category_items]),
            "strict_match_rate": safe_float_mean(
                [1.0 if item["task_metrics"]["strict_match"] else 0.0 for item in category_items]
            ),
            "avg_precision": safe_float_mean([item["task_metrics"]["precision"] for item in category_items]),
            "avg_recall": safe_float_mean([item["task_metrics"]["recall"] for item in category_items]),
            "avg_wer": safe_float_mean(
                [
                    item["transcript_metrics"]["wer"]
                    for item in category_items
                    if item.get("transcript_metrics") and item["transcript_metrics"].get("wer") is not None
                ]
            ),
        }
    return summary


def execute_pipeline(
    pipeline: str,
    case: dict[str, Any],
    cases_path: Path,
    title_threshold: float,
    skip_missing_audio: bool,
) -> dict[str, Any]:
    started = time.perf_counter()
    result: dict[str, Any] = {
        "case_id": case["id"],
        "category": case["category"],
        "pipeline": pipeline,
        "status": "ok",
        "latency_sec": None,
        "project_title": case["project_title"],
        "error": None,
        "input_preview": None,
        "predicted_tasks": [],
        "task_metrics": None,
        "transcript": None,
        "transcript_metrics": None,
        "audio_path": None,
    }
    try:
        if pipeline == TEXT_OPENROUTER:
            if not str(case.get("input_text") or "").strip():
                result["status"] = "skipped"
                result["error"] = "input_text is empty"
                return result
            result["input_preview"] = str(case["input_text"])[:400]
            predicted_tasks = run_text_openrouter(case)
        elif pipeline == TEXT_RULES:
            if not str(case.get("input_text") or "").strip():
                result["status"] = "skipped"
                result["error"] = "input_text is empty"
                return result
            result["input_preview"] = str(case["input_text"])[:400]
            predicted_tasks = run_text_rules(case)
        elif pipeline in {WHISPER_OPENROUTER, WHISPER_RULES}:
            if not str(case.get("audio_path") or "").strip():
                result["status"] = "skipped"
                result["error"] = "audio_path is empty"
                return result
            try:
                audio_path, transcript = transcribe_case_audio(case, cases_path)
            except FileNotFoundError:
                if skip_missing_audio:
                    result["status"] = "skipped"
                    result["error"] = "audio file not found"
                    return result
                raise
            result["audio_path"] = audio_path
            result["transcript"] = transcript
            result["transcript_metrics"] = {
                "wer": None,
                "cer": None,
                "similarity": None,
            }
            expected_transcript = str(case.get("expected_transcript") or "").strip()
            if expected_transcript:
                result["transcript_metrics"] = {
                    "wer": round(calc_wer(expected_transcript, transcript) or 0.0, 4),
                    "cer": round(calc_cer(expected_transcript, transcript) or 0.0, 4),
                    "similarity": round(title_similarity(expected_transcript, transcript), 4),
                }
            source_text = build_audio_source_text(case, transcript)
            result["input_preview"] = source_text[:400]
            if pipeline == WHISPER_OPENROUTER:
                predicted_tasks = extract_tasks_via_openrouter(source_text, case["project_title"])
            else:
                predicted_tasks = extract_tasks_by_rules(source_text)
        else:
            raise ValueError(f"Unsupported pipeline: {pipeline}")

        result["predicted_tasks"] = predicted_tasks
        result["task_metrics"] = match_tasks(case["expected_tasks"], predicted_tasks, title_threshold)
    except HTTPException as exc:
        result["status"] = "error"
        result["error"] = f"HTTP {exc.status_code}: {exc.detail}"
    except Exception as exc:  # noqa: BLE001
        result["status"] = "error"
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        result["latency_sec"] = round(time.perf_counter() - started, 4)
    return result


def print_case_progress(
    pipeline: str,
    index: int,
    total: int,
    case: dict[str, Any],
    result: dict[str, Any],
) -> None:
    status = result["status"]
    latency = result["latency_sec"]
    category = case["category"]
    case_id = case["id"]
    if status == "ok":
        metrics = result.get("task_metrics") or {}
        extra = f"f1={metrics.get('f1')} strict={metrics.get('strict_match')}"
    else:
        extra = result.get("error")
    print(
        f"[{pipeline}] {index}/{total} case={case_id} category={category} "
        f"status={status} latency={latency}s {extra}",
        flush=True,
    )


def print_summary(report: dict[str, Any]) -> None:
    print("=" * 88)
    print("Task Extraction Benchmark")
    print("=" * 88)
    print(f"Cases file: {report['cases_file']}")
    print(f"Executed at: {report['generated_at_epoch']}")
    print()
    for pipeline in report["pipelines"]:
        summary = report["summary"][pipeline]
        print(f"[{pipeline}]")
        print(
            "  cases="
            f"{summary['executed_cases']}/{summary['total_cases']} "
            f"errors={summary['failed_cases']} skipped={summary['skipped_cases']} "
            f"avg_latency={summary['avg_latency_sec']}"
        )
        print(
            "  quality="
            f"strict={summary['strict_match_rate']} "
            f"precision={summary['avg_precision']} "
            f"recall={summary['avg_recall']} "
            f"f1={summary['avg_f1']} "
            f"title_sim={summary['avg_title_similarity']}"
        )
        if summary["avg_wer"] is not None or summary["avg_cer"] is not None:
            print(f"  whisper=wer={summary['avg_wer']} cer={summary['avg_cer']}")
        for category, category_summary in summary["by_category"].items():
            print(
                "  - "
                f"{category}: cases={category_summary['executed_cases']} "
                f"f1={category_summary['avg_f1']} "
                f"strict={category_summary['strict_match_rate']} "
                f"precision={category_summary['avg_precision']} "
                f"recall={category_summary['avg_recall']} "
                f"wer={category_summary['avg_wer']}"
            )
        print()


def main() -> int:
    args = parse_args()
    cases_path = Path(args.cases).resolve()
    cases = load_cases(cases_path)
    pipelines = [item.strip() for item in args.pipelines.split(",") if item.strip()]
    unsupported = [item for item in pipelines if item not in ALL_PIPELINES]
    if unsupported:
        raise ValueError(f"Unsupported pipelines: {', '.join(unsupported)}")

    report: dict[str, Any] = {
        "cases_file": str(cases_path),
        "generated_at_epoch": int(time.time()),
        "pipelines": pipelines,
        "results": {pipeline: [] for pipeline in pipelines},
        "summary": {},
    }
    for pipeline in pipelines:
        print(f"Starting pipeline: {pipeline} ({len(cases)} cases)", flush=True)
        for index, case in enumerate(cases, start=1):
            result = execute_pipeline(
                pipeline=pipeline,
                case=case,
                cases_path=cases_path,
                title_threshold=args.title_threshold,
                skip_missing_audio=not args.fail_missing_audio,
            )
            report["results"][pipeline].append(result)
            print_case_progress(
                pipeline=pipeline,
                index=index,
                total=len(cases),
                case=case,
                result=result,
            )
        report["summary"][pipeline] = summarize_pipeline(report["results"][pipeline])

    print_summary(report)
    if args.output:
        output_path = Path(args.output).resolve()
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved report to: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
