#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QUALITY_PATH = ROOT / "skills/story-write/scripts/quality_lifecycle.py"
TRACKING_PATH = ROOT / "skills/story-write/scripts/tracking_commit.py"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


quality = load("quality_lifecycle_test", QUALITY_PATH)
tracking = load("quality_tracking_test", TRACKING_PATH)


def position() -> dict[str, object]:
    return {"volume": "第一卷", "volume_start_chapter": 1, "story_time": "当日", "scene": "会议室"}


def initial() -> dict[str, object]:
    return {
        "schema_version": 1,
        "book_title": "质量代际测试",
        "last_chapter": 0,
        "context": {
            "position": position(),
            "long_term_constraints": ["只写批准内容。"],
            "active_character_names": [],
            "continuity_risks": [],
            "recent_chapters": [],
            "next_chapter_commitments": [],
        },
        "character_snapshots": {},
        "foreshadow": [],
        "timeline_events": [],
    }


def transaction(chapter: int, revision: int, *, mode: str = "append") -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": mode,
        "chapter": chapter,
        "chapter_title": f"代际测试·{chapter}",
        "expected_state_revision": revision,
        "delta": {
            "result": f"第{chapter}章的决定已经发生。",
            "character_changes": [],
            "foreshadow_changes": [],
            "timeline_events": [
                {
                    "id": f"E{chapter * 2 - 1:03d}", "story_time": "当日",
                    "objective_fact": f"甲与乙关系推进到合作{chapter}。", "reader_knowledge": f"甲与乙关系推进到合作{chapter}。",
                    "reveal_status": "已揭示", "reveal_chapter": chapter, "characters": ["甲", "乙"],
                },
                {
                    "id": f"E{chapter * 2:03d}", "story_time": "当日",
                    "objective_fact": f"甲的担当推进到承担{chapter}。", "reader_knowledge": f"甲的担当推进到承担{chapter}。",
                    "reveal_status": "已揭示", "reveal_chapter": chapter, "characters": ["甲"],
                },
            ],
            "constraints": [],
            "next_chapter_commitments": ["继续已批准的目标。"],
        },
        "context": {
            "position": position(),
            "long_term_constraints": ["只写批准内容。"],
            "active_character_names": [],
            "continuity_risks": [],
        },
        "character_snapshots": {},
    }


def body_text(chapter: int, variant: int) -> str:
    # Exercise lifecycle state rather than degeneration detection. A stable
    # CJK permutation keeps the fixture at 1000 visible characters without
    # manufacturing repeated-token findings, while variant changes its hash.
    chars = "".join(chr(0x4E00 + ((index * 37 + variant) % 2000)) for index in range(999)) + "。"
    return f"# 第{chapter}章 代际测试\n{chars}"


def reader(
    reader_id: str,
    previous: str | None,
    *,
    chapter: int,
    revision: str,
    input_fingerprint: str,
) -> dict[str, object]:
    return {
        "reader_id": reader_id,
        "run_id": f"run-{reader_id}",
        "independent": True,
        "cohort_type": "sequential",
        "source_scope": {
            "accepted_prose_through": chapter - 1,
            "candidate_chapter": chapter,
            "candidate_revision": revision,
            "oracle_visible": False,
        },
        "input_fingerprint": input_fingerprint,
        "previous_hash": previous,
        "remembered": ["人物作出决定"],
        "forgotten": [],
        "believes": ["决定会有后果"],
        "guesses": ["下一步将执行决定"],
        "emotion": "理解并产生轻微期待",
        "expectation": "看到决定如何执行",
        "first_friction": "无明显摩擦",
        "strongest_read_on": "人物明确选择后的后果",
        "end_expectation": "下一章执行选择",
        "target_emotion_received": True,
        "cumulative_fatigue": "没有重复刺激疲劳",
        "retention_verdict": "pass",
        "retention_evidence": "选择和后果都可定位，愿意继续阅读。",
        "retention_issue_ids": [],
    }


def reader_v2(
    reader_id: str,
    previous: str | None,
    *,
    chapter: int,
    revision: str,
    input_fingerprint: str,
    expectation_id: str,
    target_emotion_id: str = "EMO-forward",
    delivered: bool = True,
) -> dict[str, object]:
    row = reader(reader_id, previous, chapter=chapter, revision=revision, input_fingerprint=input_fingerprint)
    profile = {"genre_familiarity": "medium", "reading_history": "sequential"}
    row.update({
        "reader_schema": quality.READER_SCHEMA_V3,
        "persona_id": "core-reader",
        "persona_profile": profile,
        "persona_profile_sha256": quality.sha_json(profile),
        "evidence_type": "llm_proxy",
        "target_emotion_received": delivered,
        "measurements": {
            "first_friction": {"present": False, "severity": 0, "quit_intent": False},
            "strongest_read_on": {
                "scene_id": "scene-1", "scene_index": 1, "start_offset": 10, "end_offset": 20,
                "function": "choice-consequence", "intensity": 4, "confidence": 0.9,
                "evidence_anchor": "人物作出选择并承担后果",
            },
            "end_expectation": {
                "expectation_ids": [expectation_id], "hypothesis_ids": ["hypothesis-a"],
                "confidence": 0.8, "free_text": "期待选择带来的后果。",
            },
            "target_emotion": {
                "target_id": target_emotion_id, "observed_emotion": "期待",
                "intensity": 4 if delivered else 1, "confidence": 0.9, "received": delivered,
            },
            "cumulative_fatigue": {"level": 0, "delta": 0, "reason": "没有累积疲劳。"},
            "cumulative_confusion": {"level": 0, "delta": 0, "reason": "当前行动与指代清楚。"},
            "mystery_fatigue": {"level": 0, "delta": 0, "reason": "没有无功能谜团累积。"},
            "first_quit_chapter": None,
            "continued_by_choice": True,
            "continued_for_study": False,
        },
    })
    return row


def p1_contract(chapter: int) -> dict[str, object]:
    return {
        "chapter_function": "推进",
        "target_emotion_id": "EMO-forward",
        "required_deliveries": ["choice-consequence"],
        "allowed_expectation_ids": [f"EX-01-{chapter:03d}"],
        "allowed_hypothesis_ids": ["hypothesis-a", "hypothesis-b"],
        "intentional_ambiguity": False,
        "scene_catalog": [
            {"scene_id": "scene-1", "scene_index": 1},
            {"scene_id": "scene-2", "scene_index": 2},
            {"scene_id": "scene-3", "scene_index": 3},
            {"scene_id": "scene-4", "scene_index": 4},
        ],
    }


CORE_PROFILE = {"genre_familiarity": "medium", "reading_history": "sequential"}


def calibrated_function_rules() -> dict[str, object]:
    return {
        "推进": {"control_kind": "standard", "allowed_deliveries": ["choice-consequence"], "require_delivery_consensus": True, "require_emotion_majority": True, "require_expectation_consensus": True},
        "低压生活": {"control_kind": "low_pressure", "allowed_deliveries": ["relationship-recovery"], "require_delivery_consensus": True, "require_emotion_majority": False, "require_expectation_consensus": True},
        "余波": {"control_kind": "aftermath", "allowed_deliveries": ["aftermath"], "require_delivery_consensus": True, "require_emotion_majority": True, "require_expectation_consensus": False},
        "有意多解": {"control_kind": "intentional_ambiguity", "allowed_deliveries": ["hypothesis-space"], "require_delivery_consensus": True, "require_emotion_majority": True, "require_expectation_consensus": True},
        "安静转场": {"control_kind": "quiet_transition", "allowed_deliveries": ["transition"], "require_delivery_consensus": True, "require_emotion_majority": False, "require_expectation_consensus": True},
    }


def calibration_measurement(calibration_id: str, reader: int, chapter: int, story: str = "story-a") -> dict[str, object]:
    return {
        "story_package_id": story,
        "chapter": chapter,
        "reader_index": reader,
        "observed_first_friction_ratio": 0.15,
        "observed_friction_severity": 3,
        "observed_read_on_intensity": 3,
        "observed_emotion_intensity": 2,
        "observed_confidence": 0.5,
        "strongest_read_on_scene": 1,
        "target_emotion_received": True,
        "cumulative_fatigue": chapter // 5,
    }


def calibration_observations(calibration_id: str, story: str = "story-a") -> list[dict[str, object]]:
    return [
        {
            "chapter": chapter,
            "reader_measurement_sha256s": [
                quality.sha_json(calibration_measurement(calibration_id, reader, chapter, story))
                for reader in range(6)
            ],
        }
        for chapter in range(1, 16)
    ]


def threshold_spec() -> dict[str, object]:
    metrics = {}
    for name, (source, comparison, integer_output, _, _) in quality.THRESHOLD_METRICS.items():
        metrics[name] = {
            "source": source,
            "comparison": comparison,
            "quantile": 0.5,
            "rounding": "nearest" if integer_output else "six_decimals",
        }
    return {
        "algorithm_version": "directional-reader-story-quantiles-v1",
        "aggregation_unit": "reader_x_story",
        "story_weighting": "equal",
        "interpolation": "linear",
        "missing_rule": "natural-quit-preserved-no-imputation",
        "metrics": metrics,
    }


def treatment_common_base(
    *,
    story_package_sha256: str | None = None,
    creative_package_sha256: str | None = None,
    context_sha256: str | None = None,
) -> dict[str, str]:
    return {
        "version": "common-base-v2",
        "reference_sha256": quality.sha_bytes(b"reference"),
        "agent_sha256": quality.sha_bytes(b"agent"),
        "model_sha256": quality.sha_bytes(b"model"),
        "context_sha256": context_sha256 or quality.sha_bytes(b"context"),
        "story_package_sha256": story_package_sha256 or quality.sha_bytes(b"story-package"),
        "creative_package_sha256": creative_package_sha256 or quality.sha_bytes(b"creative-package"),
        "author_identity_sha256": quality.sha_bytes(b"author"),
        "writer_identity_sha256": quality.sha_bytes(b"writer"),
    }


def heldout_calibration(calibration_id: str, evidence: dict[str, object], development_sha256: str) -> dict[str, object]:
    thresholds = {
        "early_friction_ratio": 0.15, "severe_friction": 3, "corroborated_quit_readers": 2,
        "minimum_read_on_intensity": 3, "minimum_emotion_intensity": 2,
        "minimum_confidence": 0.5,
    }
    personas = [{
        "persona_id": "core-reader", "persona_profile": CORE_PROFILE,
        "persona_profile_sha256": quality.sha_json(CORE_PROFILE),
        "minimum_independent": 2, "evidence_types": ["llm_proxy", "human"],
    }]
    golden_budget = [
        {"chapter": chapter, "outline_variants": 2, "prose_variants_per_outline": 1, "stop_rule": "one-per-outline"}
        for chapter in (1, 2, 3)
    ]
    return {
        "schema": quality.CALIBRATION_SCHEMA,
        "calibration_id": calibration_id,
        "purpose": "held_out_validation",
        "chapters": list(range(1, 16)),
        "reader_measurement_schema": quality.READER_SCHEMA_V3,
        "threshold_spec": threshold_spec(),
        "development_calibration_sha256": development_sha256,
        "story_packages": [{"story_package_id": "story-a"}, {"story_package_id": "story-b"}],
        "held_out": True,
        "human_validation": True,
        "human_reader_count": 6,
        "misfire_controls": ["low_pressure", "aftermath", "intentional_ambiguity", "quiet_transition"],
        "controls_passed": True,
        "minimum_reopen_loop_validated": True,
        "thresholds": thresholds,
        "function_rules": calibrated_function_rules(),
        "required_personas": personas,
        "golden_three_budget": golden_budget,
        "evidence": evidence,
        "observations": calibration_observations(calibration_id),
    }


def enforce_policy(calibration: dict[str, object], *, activated_from_chapter: int) -> dict[str, object]:
    policy = quality.default_policy()
    policy.update({
        "policy_version": "p1-enforce-test-v1",
        "strength_mode": "ENFORCE",
        "calibration_id": calibration["calibration_id"],
        "calibration_sha256": quality.sha_json(calibration),
        "activated_from_chapter": activated_from_chapter,
        "thresholds": copy.deepcopy(calibration["thresholds"]),
        "function_rules": copy.deepcopy(calibration["function_rules"]),
        "required_personas": copy.deepcopy(calibration["required_personas"]),
    })
    return policy


def review_packet(
    chapter: int,
    revision: str,
    previous_hashes: dict[str, str | None],
    *,
    kind: str = "draft",
    parent: str | None = None,
    winner: str = "candidate",
    base: dict[str, object] | None = None,
    outline_sha256: str = "",
    finding_ids: list[str] | None = None,
) -> dict[str, object]:
    base = base or {"chapters": {}}
    pending = {"chapter": chapter, "revision": revision}
    input_fingerprint = quality.reader_input_fingerprint(base, pending)
    perspectives = {
        name: {
            "verdict": "PASS",
            "findings": [],
            "execution": {
                "run_id": f"view-{name}",
                "candidate_revision": revision,
                "input_fingerprint": input_fingerprint,
                "reviewed_units": [f"chapter-{chapter}"],
                "evidence_summary": "已逐段复核当前候选与前文输入。",
            },
        }
        for name in quality.PERSPECTIVES
    }
    if kind == "revision":
        for finding_id in finding_ids or ["LOGIC-1"]:
            perspectives["story-logic"]["findings"].append({
                "id": finding_id,
                "severity": "S2",
                "disposition": "FIXED_VERIFIED",
                "evidence": "独立终验已确认候选不再出现该问题，且直接前因与后果仍成立。",
                "evidence_anchor": "场景1：人物作出选择并承担结果。",
                "gate_impacts": ["causality"],
            })
    blind = {"winner": winner}
    if kind == "revision":
        items = [
            {"label": "A", "body_sha256": revision},
            {"label": "B", "body_sha256": parent},
        ]
        criteria = ["clarity", "causality", "retention", "voice"]
        winner_label = "A" if winner == "candidate" else "B" if winner == "previous" else None
        blind.update({
            "labels_hidden": True,
            "order_randomized": True,
            "previous_revision": parent,
            "candidate_revision": revision,
            "rationale": "候选在不损害清晰度的前提下整体更好。",
            "package": {
                "items": items,
                "criteria": criteria,
                "selector_run_id": "selector-C",
                "selector_input_sha256": quality.sha_json({"items": items, "criteria": criteria}),
                "randomization_nonce": "fixture-order-1",
                "origin_key_revealed_after_selection": True,
                "winner_label": winner_label,
            },
        })
    frozen_fixture, frozen_fixture_sha256 = quality.frozen_benchmark_fixture()
    benchmark_sets = {}
    for set_name, rows in frozen_fixture["sets"].items():
        benchmark_sets[set_name] = []
        for frozen in rows:
            artifact_sha256 = frozen["artifact_sha256"]
            benchmark_sets[set_name].append({
                "id": frozen["id"],
                "artifact_text": frozen["artifact_text"],
                "artifact_sha256": artifact_sha256,
                "evaluation": {
                    "run_id": f"benchmark-{set_name}-{frozen['id']}",
                    "input_fingerprint": quality.sha_json({
                        "artifact_sha256": artifact_sha256,
                        "fixture_version": frozen_fixture["version"],
                        "evaluator_protocol": frozen_fixture["evaluator_protocol"],
                    }),
                    "observed": frozen["expected"],
                    "finding_ids": ["fixture-defect"] if frozen["expected"] == "defect" else [],
                    "evidence_summary": "独立评测运行只读取绑定文本与评测协议，再与冻结 oracle 对账。",
                },
            })
    cohort = [
        reader("reader-1", previous_hashes.get("reader-1"), chapter=chapter, revision=revision, input_fingerprint=input_fingerprint),
        reader("reader-2", previous_hashes.get("reader-2"), chapter=chapter, revision=revision, input_fingerprint=input_fingerprint),
    ]
    reader_state_hashes = []
    for row in cohort:
        normalized = copy.deepcopy(row)
        normalized["chapter"] = chapter
        normalized.pop("state_hash", None)
        reader_state_hashes.append(quality.sha_json(normalized))
    return {
        "schema": quality.PACKET_SCHEMA,
        "chapter": chapter,
        "revision": revision,
        "roles": {
            "defect_evaluator": "evaluator-A",
            "repairer": "repairer-B" if kind == "revision" else None,
            "holistic_selector": "selector-C",
            "final_validator": "validator-D",
        },
        "correctness_gate": {"causality": "PASS", "facts": "PASS", "present_action": "PASS", "mystery_legitimacy": "PASS"},
        "perspectives": perspectives,
        "repair": {"attempt": 1 if kind == "revision" else 0, "repeated_finding_ids": []},
        "blind_ab": blind,
        "selection_protocol": {
            "improvement_dimensions": {
                "retention": "better", "emotion_delivery": "equal", "voice": "equal",
                "memory_points": "equal", "genre_contract": "equal",
            },
            "positive_benchmark": {
                "structural_function_only": True,
                "fixture_version": frozen_fixture["version"],
                "fixture_sha256": frozen_fixture_sha256,
                **benchmark_sets,
                "dataset_sha256": quality.sha_json(benchmark_sets),
            },
            "dialogue_test": {
                "applicable": False,
                "reason": "本测试正文没有声线承载台词。",
                "voice_bearing_line_count": 0,
                "evidence": "正文 fixture 仅含叙述字符。",
            },
            "variants": {"premarked_key_chapter": False},
        },
        "reader_evidence": {
            "cohort": cohort,
            "retention_decision": "pass",
            "judge": {
                "judge_id": "reader-judge",
                "run_id": "run-reader-judge",
                "must_know": ["决定发生"], "may_believe": [], "must_not_know": [],
                "open_ids": [f"EX-01-{chapter:03d}"], "status": "PASS",
                "input_fingerprint": quality.sha_json({
                    "outline_sha256": outline_sha256,
                    "reader_state_hashes": reader_state_hashes,
                }),
                "oracle_visible_to_readers": False,
            },
        },
        "outline_contract": {
            "ending_beat_id": f"EB-01-{chapter:03d}", "ending_beat_type": "choice",
            "expectation_id": f"EX-01-{chapter:03d}", "expectation_type": "aftermath",
            "reader_oracle": {
                "must_know": "[决定发生]", "may_believe": "[]",
                "must_not_know": "[幕后原因]", "open_ids": f"[EX-01-{chapter:03d}]",
            },
            "reader_oracle_sha256": quality.sha_json({
                "must_know": "[决定发生]", "may_believe": "[]",
                "must_not_know": "[幕后原因]", "open_ids": f"[EX-01-{chapter:03d}]",
            }),
        },
        "posthoc_extraction": {
            "complete": True,
            "observations": [{"evidence": "人物明确作出选择"}],
            "authoritative_events": [
                {
                    "id": f"REL-{chapter}-{revision[:6]}", "kind": "relation", "confidence": "explicit",
                    "occurrence_state": "occurred", "evidence": "两人由陌生转为合作",
                    "tracking_event_id": f"E{chapter * 2 - 1:03d}",
                    "tracking_event_fingerprint": quality.tracking_event_fingerprint(transaction(chapter, 0)["delta"]["timeline_events"][0]),
                    "data": {"subject": "甲", "object": "乙", "relation": "合作", "before": "陌生" if chapter == 1 else f"合作{chapter - 1}", "after": f"合作{chapter}", "trigger": "共同决定"},
                },
                {
                    "id": f"ARC-{chapter}-{revision[:6]}", "kind": "arc", "confidence": "strongly_implied",
                    "occurrence_state": "occurred", "evidence": "甲主动承担后果",
                    "tracking_event_id": f"E{chapter * 2:03d}",
                    "tracking_event_fingerprint": quality.tracking_event_fingerprint(transaction(chapter, 0)["delta"]["timeline_events"][1]),
                    "data": {"character": "甲", "dimension": "担当", "before": "回避" if chapter == 1 else f"承担{chapter - 1}", "after": f"承担{chapter}", "trigger": "作出选择"},
                },
            ],
        },
        "final_validation": {
            "status": "PASS",
            "validator": "validator-D",
            "execution": {
                "run_id": "validator-D",
                "candidate_revision": revision,
                "input_fingerprint": input_fingerprint,
                "reviewed_units": [f"chapter-{chapter}", "all-findings", "reader-evidence"],
                "evidence_summary": "已完整读取候选、所有 finding 裁决与读者证据后终验。",
            },
        },
    }


class QualityLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="quality-lifecycle-")
        self.root = Path(self.temporary.name)
        self.project = self.root / "book"
        self.project.mkdir()
        (self.project / "大纲").mkdir()
        (self.project / "正文").mkdir()
        (self.project / "草稿/待验收").mkdir(parents=True)
        tracking.initialize(self.project, initial())
        quality.initialize(self.project)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_json(self, name: str, value: object) -> Path:
        path = self.root / name
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return path

    def record_evidence(self, name: str, *, kind: str, source_kind: str, artifact: dict[str, object]) -> str:
        bundle = {
            "schema": quality.EVIDENCE_BUNDLE_SCHEMA,
            "evidence_id": name,
            "kind": kind,
            "source_kind": source_kind,
            "synthetic": source_kind == "synthetic_fixture",
            "collected_at": "2026-01-01T00:00:00Z",
            "producer_run_id": f"producer-{name}",
            "artifact": artifact,
            "artifact_sha256": quality.sha_json(artifact),
        }
        result = quality.record_evidence_bundle(self.project, self.write_json(f"evidence-{name}.json", bundle))
        return str(result["evidence_sha256"])

    def install_heldout_calibration(self, calibration_id: str) -> dict[str, object]:
        # Unit fixtures model imported external evidence; production code verifies
        # each immutable artifact and never accepts synthetic_fixture for ENFORCE.
        thresholds = {
            "early_friction_ratio": 0.15, "severe_friction": 3, "corroborated_quit_readers": 2,
            "minimum_read_on_intensity": 3, "minimum_emotion_intensity": 2, "minimum_confidence": 0.5,
        }
        function_rules = calibrated_function_rules()
        personas = [{
            "persona_id": "core-reader", "persona_profile": CORE_PROFILE,
            "persona_profile_sha256": quality.sha_json(CORE_PROFILE),
            "minimum_independent": 2, "evidence_types": ["llm_proxy", "human"],
        }]
        golden_budget = [
            {"chapter": chapter, "outline_variants": 2, "prose_variants_per_outline": 1, "stop_rule": "one-per-outline"}
            for chapter in (1, 2, 3)
        ]

        development_package_hashes = []
        development_ids = ("dev-story-a", "dev-story-b")
        for package_id in development_ids:
            creative = {"genre": "legal", "premise": f"development-{calibration_id}-{package_id}"}
            artifact = {
                "story_package_id": package_id,
                "chapters": [
                    {
                        "chapter": chapter,
                        "body": f"{package_id}-body-{chapter}",
                        "revision": quality.sha_bytes(f"{package_id}-body-{chapter}".encode()),
                        "outline": f"{package_id}-outline-{chapter}",
                        "outline_sha256": quality.sha_bytes(f"{package_id}-outline-{chapter}".encode()),
                    }
                    for chapter in range(1, 16)
                ],
                "creative_package": creative,
                "creative_package_sha256": quality.sha_json(creative),
            }
            development_package_hashes.append(self.record_evidence(
                f"{calibration_id}-{package_id}", kind="story_package", source_kind="development_original", artifact=artifact,
            ))
        development_readers = [
            {
                "reader_id": f"dev-reader-{index}", "blind_code": f"dev-blind-{index}", "evidence_type": "human",
                "raw_observations": {"chapter_measurements": {
                    package_id: [calibration_measurement(calibration_id, index, chapter, package_id) for chapter in range(1, 16)]
                    for package_id in development_ids
                }},
                "persona_id": "core-reader", "persona_profile": CORE_PROFILE,
                "persona_profile_sha256": quality.sha_json(CORE_PROFILE),
            }
            for index in range(6)
        ]
        for reader in development_readers:
            reader["raw_observation_sha256"] = quality.sha_json(reader["raw_observations"])
        development_observations = calibration_observations(calibration_id, development_ids[0])
        development_human_hash = self.record_evidence(
            f"{calibration_id}-development-humans", kind="human_reader_import", source_kind="human_blind_import",
            artifact={
                "story_package_ids": list(development_ids), "reader_count": len(development_readers),
                "readers": development_readers, "calibration_observations": development_observations,
            },
        )
        development_evidence_input = {
            "story_package_sha256s": development_package_hashes,
            "human_reader_import_sha256": development_human_hash,
        }
        development = {
            "schema": quality.CALIBRATION_SCHEMA,
            "calibration_id": f"{calibration_id}-development",
            "purpose": "development_thresholds",
            "chapters": list(range(1, 16)),
            "reader_measurement_schema": quality.READER_SCHEMA_V3,
            "threshold_spec": threshold_spec(),
            "story_packages": [{"story_package_id": package_id} for package_id in development_ids],
            "held_out": False,
            "human_reader_count": len(development_readers),
            "thresholds": thresholds,
            "function_rules": function_rules,
            "required_personas": personas,
            "golden_three_budget": golden_budget,
            "evidence": {**development_evidence_input, "input_fingerprint": quality.sha_json(development_evidence_input)},
            "observations": development_observations,
        }
        quality.record_calibration(self.project, self.write_json(f"{calibration_id}-development.json", development))
        development_sha256 = quality.sha_json(development)

        package_hashes = []
        for package_id in ("story-a", "story-b"):
            creative = {"genre": "legal", "premise": f"frozen-{calibration_id}-{package_id}"}
            artifact = {
                "story_package_id": package_id,
                "chapters": [
                    {
                        "chapter": chapter,
                        "body": f"{package_id}-body-{chapter}",
                        "revision": quality.sha_bytes(f"{package_id}-body-{chapter}".encode()),
                        "outline": f"{package_id}-outline-{chapter}",
                        "outline_sha256": quality.sha_bytes(f"{package_id}-outline-{chapter}".encode()),
                    }
                    for chapter in range(1, 16)
                ],
                "creative_package": creative,
                "creative_package_sha256": quality.sha_json(creative),
            }
            package_hashes.append(self.record_evidence(f"{calibration_id}-{package_id}", kind="story_package", source_kind="held_out_original", artifact=artifact))

        human_readers = [
            {
                "reader_id": f"cal-reader-{index}", "blind_code": f"cal-blind-{index}",
                "evidence_type": "human",
                "raw_observations": {
                    "chapter_measurements": {
                        "story-a": [
                            calibration_measurement(calibration_id, index, chapter)
                            for chapter in range(1, 16)
                        ],
                        "story-b": [
                            calibration_measurement(calibration_id, index, chapter, "story-b")
                            for chapter in range(1, 16)
                        ],
                    },
                    "control_results": {
                        control_kind: {"function_delivered": True, "false_positive_detected": False}
                        for control_kind in ("low_pressure", "aftermath", "intentional_ambiguity", "quiet_transition")
                    },
                },
                "persona_id": "core-reader", "persona_profile": CORE_PROFILE,
                "persona_profile_sha256": quality.sha_json(CORE_PROFILE),
            }
            for index in range(6)
        ]
        for reader in human_readers:
            reader["raw_observation_sha256"] = quality.sha_json(reader["raw_observations"])
        human_hash = self.record_evidence(
            f"{calibration_id}-humans", kind="human_reader_import", source_kind="human_blind_import",
            artifact={
                "story_package_ids": ["story-a", "story-b"],
                "reader_count": len(human_readers),
                "readers": human_readers,
                "calibration_observations": calibration_observations(calibration_id),
            },
        )
        control_names = {
            "low_pressure": "低压生活", "aftermath": "余波",
            "intentional_ambiguity": "有意多解", "quiet_transition": "安静转场",
        }
        control_hashes = {}
        for control_kind, function_name in control_names.items():
            reader_results = [
                {
                    "reader_id": reader["reader_id"],
                    "result": reader["raw_observations"]["control_results"][control_kind],
                    "result_sha256": quality.sha_json(reader["raw_observations"]["control_results"][control_kind]),
                }
                for reader in human_readers[:2]
            ]
            control_hashes[control_kind] = self.record_evidence(
                f"{calibration_id}-control-{control_kind}", kind="misfire_control", source_kind="human_blind_import",
                artifact={
                    "control_kind": control_kind, "story_package_id": "story-a", "function_rule_name": function_name,
                    "reader_evidence_bundle_sha256": human_hash,
                    "reader_results": reader_results,
                    "status": "PASS",
                },
            )
        case_histories = [
            {"case_id": f"case-{calibration_id}-l1", "level": "L1", "states": ["OPEN", "SELECTED"]},
            {"case_id": f"case-{calibration_id}-l2", "level": "L2", "states": ["OPEN", "L3_PROPOSAL_REQUIRED"]},
            {"case_id": f"case-{calibration_id}-l3", "level": "L3", "states": ["OPEN", "SELECTED"]},
        ]
        for history in case_histories:
            for state in history["states"]:
                quality.write_reopen_case(self.project, {
                    "schema": quality.REOPEN_SCHEMA,
                    "case_id": history["case_id"],
                    "level": history["level"],
                    "state": state,
                    "created_at": "2026-01-01T00:00:00Z",
                })
        reopen_hash = self.record_evidence(
            f"{calibration_id}-reopen", kind="reopen_validation", source_kind="accepted_lifecycle",
            artifact={
                "levels_validated": ["L1", "L2", "L3"],
                "case_histories": case_histories,
                "case_history_sha256s": [quality.sha_json(history) for history in case_histories],
                "pass_exit_observed": True, "all_flat_escalation_observed": True,
            },
        )
        evidence_input = {
            "story_package_sha256s": package_hashes,
            "human_reader_import_sha256": human_hash,
            "misfire_control_sha256s": control_hashes,
            "reopen_validation_sha256": reopen_hash,
        }
        evidence = {**evidence_input, "input_fingerprint": quality.sha_json(evidence_input)}
        calibration = heldout_calibration(calibration_id, evidence, development_sha256)
        quality.record_calibration(self.project, self.write_json(f"{calibration_id}-calibration.json", calibration))
        return calibration

    def record_reopen_human_evidence(
        self,
        case: dict[str, object],
        *,
        synthetic: bool,
        arm_order: list[str],
        outcome: str,
        winner_arm_id: str | None,
    ) -> str:
        case_id = str(case["case_id"])
        arms = {str(row["arm_id"]): row for row in case["arms"]}
        readers = [
            {
                "reader_id": f"selector-reader-{index}", "blind_code": f"selector-blind-{index}",
                "evidence_type": "human",
                "raw_observations": {
                    "case_id": case_id,
                    "blinded": True,
                    "arm_order": arm_order if index == 1 else list(reversed(arm_order)),
                    "arm_observations": [
                        {
                            "arm_id": arm_id,
                            "body_sha256": arms[arm_id]["body_sha256"],
                            "outline_sha256": arms[arm_id]["outline_sha256"],
                            "strength_status": arms[arm_id]["strength_status"],
                        }
                        for arm_id in (arm_order if index == 1 else list(reversed(arm_order)))
                    ],
                    "outcome": outcome,
                    "winner_arm_id": winner_arm_id,
                },
                "persona_id": "core-reader", "persona_profile": CORE_PROFILE,
                "persona_profile_sha256": quality.sha_json(CORE_PROFILE),
            }
            for index in (1, 2)
        ]
        for reader in readers:
            reader["raw_observation_sha256"] = quality.sha_json(reader["raw_observations"])
        return self.record_evidence(
            f"selector-{quality.sha_bytes((case_id + outcome).encode())[:12]}", kind="human_reader_import",
            source_kind="synthetic_fixture" if synthetic else "human_blind_import",
            artifact={"story_package_ids": [case_id], "reader_count": 2, "readers": readers},
        )

    def reopen_arm_metadata(
        self,
        case: dict[str, object],
        arm_id: str,
        body: Path,
        *,
        outline: Path | None = None,
        delivered: bool,
    ) -> dict[str, object]:
        chapter = int(case["chapter"])
        outline_sha256 = quality.sha_file(outline) if outline is not None else str(case["outline_sha256"])
        contract = quality.outline_contract(outline) if outline is not None else copy.deepcopy(case["outline_contract"])
        cohort = [
            reader_v2(
                f"{arm_id}-reader-{index}", None, chapter=chapter, revision=quality.sha_file(body),
                input_fingerprint=quality.sha_bytes(f"{arm_id}-input".encode()),
                expectation_id=f"EX-01-{chapter:03d}", delivered=delivered,
            )
            for index in (1, 2)
        ]
        pseudo = {
            "chapter": chapter, "revision": quality.sha_file(body), "outline_contract": contract,
            "quality_policy_sha256": case["quality_policy_sha256"],
        }
        strength = quality.derive_strength_gate(pseudo, case["quality_policy"], cohort)
        evidence_hashes = [quality.sha_json(row) for row in cohort]
        evaluation_input = {
            "body_sha256": quality.sha_file(body), "outline_sha256": outline_sha256,
            "policy_sha256": case["quality_policy_sha256"], "reader_evidence_sha256s": evidence_hashes,
        }
        return {
            "schema": quality.REOPEN_SCHEMA, "arm_id": arm_id, "writer_run_id": f"writer-{arm_id}",
            "generation_budget": 1, "stop_rule": "one-version-per-arm",
            "body_sha256": quality.sha_file(body), "outline_sha256": outline_sha256,
            "evaluation": {
                "evaluator_run_id": f"evaluator-{arm_id}", "reader_evidence": cohort,
                "strength_gate": {**strength, "derived": True},
                "input_fingerprint": quality.sha_json(evaluation_input),
            },
        }

    def resolve_reopen(
        self,
        case_id: str,
        *,
        arm_order: list[str],
        outcome: str,
        winner_arm_id: str | None,
        synthetic: bool,
        prefix: str,
        evidence_sha256: str | None = None,
    ) -> dict[str, object]:
        case = quality.load_reopen_case(self.project, case_id)
        criteria = ["chapter-function", "emotion-delivery", "retention"]
        selector_input = {
            "arms": [
                {
                    "arm_id": row["arm_id"],
                    "body_sha256": row["body_sha256"],
                    "outline_sha256": row["outline_sha256"],
                    "strength_status": row["strength_status"],
                    "strength_gate_sha256": row["strength_gate_sha256"],
                }
                for row in case["arms"]
            ],
            "arm_order": arm_order,
            "criteria": criteria,
        }
        if evidence_sha256 is None:
            evidence_sha256 = self.record_reopen_human_evidence(
                case, synthetic=synthetic, arm_order=arm_order, outcome=outcome,
                winner_arm_id=winner_arm_id,
            )
        validation_input = {
            "selector_input_sha256": quality.sha_json(selector_input),
            "outcome": outcome,
            "winner_arm_id": winner_arm_id,
            "evidence_bundle_sha256": evidence_sha256,
        }
        decision = {
            "schema": quality.REOPEN_SCHEMA,
            "blinded": True,
            "order_randomized": True,
            "arm_order": arm_order,
            "selector_run_id": f"{prefix}-selector",
            "randomization_nonce": f"{prefix}-random-order",
            "selection_criteria": criteria,
            "selector_input_sha256": quality.sha_json(selector_input),
            "outcome": outcome,
            "winner_arm_id": winner_arm_id,
            "held_out_final_validation": {
                "run_id": f"{prefix}-heldout-validator",
                "evidence_bundle_sha256": evidence_sha256,
                "input_fingerprint": quality.sha_json(validation_input),
                "status": "PASS",
            },
        }
        return quality.resolve_reopen_case(
            self.project,
            case_id,
            self.write_json(f"{prefix}-decision.json", decision),
        )

    def run_cli(self, *arguments: object, expect: int = 0) -> dict[str, object]:
        completed = subprocess.run(
            [sys.executable, str(QUALITY_PATH), *(str(argument) for argument in arguments)],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            expect,
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        self.assertTrue(lines, f"quality lifecycle CLI emitted no JSON: {completed.stderr}")
        value = json.loads(lines[-1])
        self.assertIsInstance(value, dict)
        return value

    def write_chapter_inputs(self, chapter: int, variant: int, *, mode: str = "append") -> tuple[Path, Path]:
        (self.project / "大纲" / f"细纲_第{chapter:03d}章.md").write_text(
            f"- 字数目标：1000 字\n- 字数口径：visible_chars_v1\n- 结尾拍ID/类型：EB-01-{chapter:03d}；choice；作出决定\n"
            f"- 期待ID/类型：EX-01-{chapter:03d}；aftermath；决定的后果\n"
            f"- 读者验收预期：must_know=[决定发生]；may_believe=[]；must_not_know=[幕后原因]；open_ids=[EX-01-{chapter:03d}]\n"
            "| # | 情节点（谁做了什么） | 功能标签 | 执行边界 |\n|---|---|---|---|\n| 1 | 甲作出决定 | 推进 | 不新增支线 |\n",
            encoding="utf-8",
        )
        candidate = self.project / "草稿/待验收" / f"第{chapter:03d}章_代际测试.md"
        candidate.write_text(body_text(chapter, variant), encoding="utf-8")
        state = tracking.load_state(self.project)
        txn = self.write_json(f"txn-{chapter}-{variant}.json", transaction(chapter, state["state_revision"], mode=mode))
        return candidate, txn

    def write_p1_chapter_inputs(self, chapter: int, variant: int, *, mode: str = "append") -> tuple[Path, Path]:
        candidate, txn = self.write_chapter_inputs(chapter, variant, mode=mode)
        outline = self.project / "大纲" / f"细纲_第{chapter:03d}章.md"
        text = outline.read_text(encoding="utf-8")
        text = text.replace(
            "| 1 | 甲作出决定 | 推进 | 不新增支线 |\n",
            "| 1 | 甲看到当前证据 | 铺垫 | 不新增支线 |\n"
            "| 2 | 甲确认自己的目标 | 推进 | 不新增支线 |\n"
            "| 3 | 甲作出决定 | 选择 | 不新增支线 |\n"
            "| 4 | 决定产生可见后果 | 结果 | 不新增支线 |\n",
        )
        text += "- P1质量契约：" + json.dumps(p1_contract(chapter), ensure_ascii=False, separators=(",", ":")) + "\n"
        outline.write_text(text, encoding="utf-8")
        return candidate, txn

    def open_close_p0_run(
        self,
        chapter: int,
        variant: int,
        *,
        run_id: str,
        common_base: dict[str, str] | None = None,
    ) -> tuple[Path, Path, dict[str, object], dict[str, object]]:
        body, txn = self.write_chapter_inputs(chapter, variant)
        start = {
            "schema": quality.TREATMENT_RUN_SCHEMA,
            "run_id": run_id,
            "chapter": chapter,
            "treatment": "P0",
            "treatment_version": "p0-single-draft-v1",
            "common_base": copy.deepcopy(common_base or treatment_common_base()),
            "budget": {"creative_attempts": 1, "max_defect_repairs": 1, "max_visible_chars": 5000},
            "stop_rule": "one-creative-attempt-one-local-correctness-repair",
            "premise_interest_pre_read": {"status": "not_collected", "reason": "engineering shadow smoke"},
        }
        opened = self.run_cli(
            "open-treatment-run", "--project", self.project,
            "--input", self.write_json(f"{run_id}-open.json", start),
        )
        digest = quality.sha_file(body)
        close = {
            "schema": quality.TREATMENT_RUN_SCHEMA,
            "run_id": run_id,
            "treatment": "P0",
            "single_draft": {
                "body_sha256": digest,
                "initial_body_sha256": digest,
                "writer_run_id": f"writer-{run_id}",
                "generation_attempts": 1,
                "defect_repairs": [],
            },
        }
        closed = self.run_cli(
            "close-treatment-run", "--project", self.project, "--run", run_id,
            "--input", self.write_json(f"{run_id}-close.json", close),
            "--single-body", body, "--single-original-body", body,
        )
        return body, txn, opened, closed

    def test_p0_single_draft_run_is_immutable_and_stageable(self) -> None:
        bad_start = {
            "schema": quality.TREATMENT_RUN_SCHEMA,
            "run_id": "p0-hidden-resample",
            "chapter": 1,
            "treatment": "P0",
            "treatment_version": "p0-single-draft-v1",
            "common_base": treatment_common_base(),
            "budget": {"creative_attempts": 2, "max_defect_repairs": 1, "max_visible_chars": 5000},
            "stop_rule": "one-draft",
            "premise_interest_pre_read": {"status": "not_collected", "reason": "negative fixture"},
        }
        self.write_chapter_inputs(1, 1)
        with self.assertRaisesRegex(quality.QualityError, "at most 1"):
            quality.open_treatment_run(self.project, self.write_json("p0-hidden-resample.json", bad_start))

        over_start = copy.deepcopy(bad_start)
        over_start["run_id"] = "p0-over-budget"
        over_start["budget"] = {"creative_attempts": 1, "max_defect_repairs": 0, "max_visible_chars": 500}
        quality.open_treatment_run(self.project, self.write_json("p0-over-budget-open.json", over_start))
        over_body = self.project / "草稿/待验收/第001章_超预算.md"
        over_body.write_text("# 第1章 超预算\n" + "字" * 600, encoding="utf-8")
        over_hash = quality.sha_file(over_body)
        over_close = {
            "schema": quality.TREATMENT_RUN_SCHEMA,
            "run_id": "p0-over-budget",
            "treatment": "P0",
            "single_draft": {
                "body_sha256": over_hash,
                "initial_body_sha256": over_hash,
                "writer_run_id": "writer-p0-over-budget",
                "generation_attempts": 1,
                "defect_repairs": [],
            },
        }
        with self.assertRaisesRegex(quality.QualityError, "exceeds the frozen visible-character budget"):
            quality.close_treatment_run(
                self.project, "p0-over-budget", self.write_json("p0-over-budget-close.json", over_close),
                single_body=over_body, single_original_body=over_body,
            )

        body, txn, opened, closed = self.open_close_p0_run(1, 1, run_id="p0-single-001")
        self.assertEqual((opened["treatment"], closed["selected_label"]), ("P0", "single_draft"))
        wrong = self.project / "草稿/待验收/第001章_错误重采样.md"
        wrong.write_text(body_text(1, 2), encoding="utf-8")
        with self.assertRaisesRegex(quality.QualityError, "selected body"):
            quality.stage(
                self.project, 1, wrong, txn, kind="draft", resolution="within_user_band",
                metadata={"treatment_run_id": "p0-single-001"},
            )
        staged = self.run_cli(
            "stage", "--project", self.project, "--chapter", 1,
            "--candidate", body, "--tracking-input", txn, "--kind", "draft",
            "--metadata", json.dumps({"treatment_run_id": "p0-single-001"}),
        )
        base = quality.manifest_for(self.project)
        packet = review_packet(
            1, staged["revision"], {"reader-1": None, "reader-2": None},
            base=base, outline_sha256=staged["outline_sha256"],
        )
        review_path = self.write_json("p0-single-review.json", packet)
        self.run_cli("certify", "--project", self.project, "--pending", staged["pending_id"], "--input", review_path)
        pending_path = quality.quality_root(self.project) / "pending" / staged["pending_id"] / "pending.json"
        original_pending = quality.read_json(pending_path, "P0 pending fixture")
        tampered_pending = copy.deepcopy(original_pending)
        tampered_pending["treatment_run_id"] = "nonexistent-treatment-run"
        tampered_pending["treatment"] = "P1"
        tampered_pending["treatment_close_boundary_sha256"] = quality.sha_bytes(b"forged-close")
        quality.atomic_json(pending_path, tampered_pending)
        with self.assertRaisesRegex(quality.QualityError, "pending generation changed after certification"):
            quality.accept(self.project, staged["pending_id"])
        quality.atomic_json(pending_path, original_pending)
        accepted = self.run_cli("accept", "--project", self.project, "--pending", staged["pending_id"])
        chapter = quality.manifest_for(self.project)["chapters"]["1"]
        self.assertEqual(chapter["revision"], closed["selected_body_sha256"])
        self.assertEqual(chapter["treatment_provenance"], {
            "treatment": "P0",
            "run_id": "p0-single-001",
            "start_boundary_sha256": opened["start_boundary_sha256"],
            "close_boundary_sha256": closed["close_boundary_sha256"],
        })
        self.assertEqual(accepted["generation_id"], quality.head_record(self.project)["generation_id"])
        artifact = self.project / ".story-quality/treatment-runs/p0-single-001/artifacts/single-draft.md"
        artifact.write_text("tampered P0 body", encoding="utf-8")
        with self.assertRaisesRegex(quality.QualityError, "artifact hash mismatch"):
            quality.load_treatment_run(self.project, "p0-single-001", require_closed=True)

    def test_accepted_p0_workflow_receipt_binds_final_generation(self) -> None:
        creative_package = {"genre": "legal", "premise": "accepted P0 workflow fixture"}
        story_package_id = "accepted-p0-package"
        package_chapters = []
        for chapter in range(1, 16):
            self.write_chapter_inputs(chapter, 100 + chapter)
            outline_path = self.project / "大纲" / f"细纲_第{chapter:03d}章.md"
            outline_text = outline_path.read_text(encoding="utf-8")
            body = body_text(chapter, 100 + chapter)
            package_chapters.append({
                "chapter": chapter,
                "body": body,
                "revision": quality.sha_bytes(body.encode()),
                "outline": outline_text,
                "outline_sha256": quality.sha_bytes(outline_text.strip().encode()),
            })
        package_artifact = {
            "story_package_id": story_package_id,
            "chapters": package_chapters,
            "creative_package": creative_package,
            "creative_package_sha256": quality.sha_json(creative_package),
        }
        package_sha256 = self.record_evidence(
            "accepted-p0-story-package", kind="story_package",
            source_kind="development_original", artifact=package_artifact,
        )
        common_base = treatment_common_base(
            story_package_sha256=quality.sha_json(package_artifact),
            creative_package_sha256=quality.sha_json(creative_package),
        )
        run_ids = []
        for chapter in range(1, 16):
            run_id = f"p0-workflow-{chapter:03d}"
            self.open_close_p0_run(chapter, 100 + chapter, run_id=run_id, common_base=common_base)
            self.stage_certify_accept(chapter, 100 + chapter, treatment_run_id=run_id)
            run_ids.append(run_id)
        runs = [quality.load_treatment_run(self.project, run_id, require_closed=True) for run_id in run_ids]
        outputs = [
            {"chapter": chapter, "revision": run["close"]["selected_body_sha256"]}
            for chapter, run in enumerate(runs, 1)
        ]
        head = quality.head_record(self.project)
        control_rows = [
            {
                "chapter": run["open"]["chapter"],
                "reference_sha256": run["open"]["common_base"]["reference_sha256"],
                "agent_sha256": run["open"]["common_base"]["agent_sha256"],
                "model_sha256": run["open"]["common_base"]["model_sha256"],
                "context_sha256": run["open"]["common_base"]["context_sha256"],
                "story_package_sha256": run["open"]["common_base"]["story_package_sha256"],
                "creative_package_sha256": run["open"]["common_base"]["creative_package_sha256"],
                "author_identity_sha256": run["open"]["common_base"]["author_identity_sha256"],
                "writer_identity_sha256": run["open"]["common_base"]["writer_identity_sha256"],
                "outline_sha256": run["open"]["outline_sha256"],
                "max_visible_chars": run["open"]["budget"]["max_visible_chars"],
            }
            for run in runs
        ]
        common_provenance = {
            "creative_package_sha256": common_base["creative_package_sha256"],
            "author_identity_sha256": common_base["author_identity_sha256"],
            "writer_identity_sha256": common_base["writer_identity_sha256"],
            "model_identity_sha256": common_base["model_sha256"],
            "context_sha256": quality.sha_json([common_base["context_sha256"] for _ in runs]),
        }
        workflow = {
            "story_package_id": story_package_id,
            "treatment": "P0",
            "workflow_version": "p0-single-draft-v1",
            "run_id": "accepted-p0-workflow",
            "started_at": min(run["open"]["received_at"] for run in runs),
            "completed_at": max(run["close"]["received_at"] for run in runs),
            "story_package_evidence_sha256": package_sha256,
            "outputs": outputs,
            "variant_budget": {"P0": 1, "P1": 2},
            "shared_max_visible_chars": 5000,
            "common_control_sha256": quality.sha_json(control_rows),
            "common_provenance": common_provenance,
            "treatment_budget_sha256": quality.sha_json(runs[0]["open"]["budget"]),
            "outline_sha256s": [run["open"]["outline_sha256"] for run in runs],
            "stop_rule": "one-creative-attempt-one-local-correctness-repair",
            "output_fingerprint": quality.sha_json(outputs),
            "treatment_run_ids": run_ids,
            "accepted_generation_id": head["generation_id"],
            "accepted_manifest_sha256": head["manifest_sha256"],
        }
        workflow_sha256 = self.record_evidence(
            "accepted-p0-workflow", kind="workflow_run",
            source_kind="accepted_lifecycle", artifact=workflow,
        )
        self.assertTrue(quality.is_sha256(workflow_sha256))

        wrong_manifest = copy.deepcopy(workflow)
        wrong_manifest["accepted_manifest_sha256"] = quality.sha_bytes(b"not-the-final-manifest")
        bundle = {
            "schema": quality.EVIDENCE_BUNDLE_SCHEMA,
            "evidence_id": "accepted-p0-wrong-manifest",
            "kind": "workflow_run",
            "source_kind": "accepted_lifecycle",
            "synthetic": False,
            "collected_at": "2026-01-01T00:00:00Z",
            "producer_run_id": "producer-accepted-p0-wrong-manifest",
            "artifact": wrong_manifest,
            "artifact_sha256": quality.sha_json(wrong_manifest),
        }
        with self.assertRaisesRegex(quality.QualityError, "accepted manifest hash mismatch"):
            quality.validate_evidence_bundle(bundle, self.project)
        wrong_budget = copy.deepcopy(workflow)
        wrong_budget["variant_budget"]["P0"] = 2
        budget_bundle = {
            **bundle,
            "evidence_id": "accepted-p0-wrong-budget",
            "producer_run_id": "producer-accepted-p0-wrong-budget",
            "artifact": wrong_budget,
            "artifact_sha256": quality.sha_json(wrong_budget),
        }
        with self.assertRaisesRegex(quality.QualityError, "variant budget differs from treatment starts"):
            quality.validate_evidence_bundle(budget_bundle, self.project)

    def test_p0_defect_repair_chain_preserves_every_body_version(self) -> None:
        original, _ = self.write_chapter_inputs(1, 201)
        repaired = self.project / "草稿/待验收/第001章_确定性修复.md"
        repaired.write_text(body_text(1, 202), encoding="utf-8")
        run_id = "p0-repair-chain"
        start = {
            "schema": quality.TREATMENT_RUN_SCHEMA,
            "run_id": run_id,
            "chapter": 1,
            "treatment": "P0",
            "treatment_version": "p0-single-draft-v1",
            "common_base": treatment_common_base(),
            "budget": {"creative_attempts": 1, "max_defect_repairs": 1, "max_visible_chars": 5000},
            "stop_rule": "one-creative-attempt-one-local-correctness-repair",
            "premise_interest_pre_read": {"status": "not_collected", "reason": "repair-chain fixture"},
        }
        self.run_cli(
            "open-treatment-run", "--project", self.project,
            "--input", self.write_json("p0-repair-open.json", start),
        )
        original_hash = quality.sha_file(original)
        repaired_hash = quality.sha_file(repaired)
        close = {
            "schema": quality.TREATMENT_RUN_SCHEMA,
            "run_id": run_id,
            "treatment": "P0",
            "single_draft": {
                "body_sha256": repaired_hash,
                "initial_body_sha256": original_hash,
                "writer_run_id": "writer-p0-repair-chain",
                "generation_attempts": 1,
                "defect_repairs": [{
                    "repair_index": 1,
                    "repair_id": "repair-logic-001",
                    "finding_ids": ["LOGIC-001"],
                    "repair_scope": "local",
                    "before_body_sha256": original_hash,
                    "after_body_sha256": repaired_hash,
                    "evaluator_run_id": "evaluator-p0-repair-chain",
                }],
            },
        }
        wrong_intermediate = self.project / "草稿/待验收/第001章_错误中间修复.md"
        wrong_intermediate.write_text(body_text(1, 203), encoding="utf-8")
        with self.assertRaisesRegex(quality.QualityError, "differs from its immutable version artifact"):
            quality.close_treatment_run(
                self.project, run_id, self.write_json("p0-repair-wrong-artifact.json", close),
                single_body=repaired, single_original_body=original,
                single_repair_bodies=[wrong_intermediate],
            )
        self.run_cli(
            "close-treatment-run", "--project", self.project, "--run", run_id,
            "--input", self.write_json("p0-repair-close.json", close),
            "--single-body", repaired,
            "--single-original-body", original,
            "--single-repair-body", repaired,
        )
        run = quality.load_treatment_run(self.project, run_id, require_closed=True)
        self.assertEqual(run["close"]["single_draft"]["version_body_sha256s"], [original_hash, repaired_hash])
        original_artifact = self.project / ".story-quality/treatment-runs/p0-repair-chain/artifacts/single-original.md"
        original_artifact.write_text("tampered original version", encoding="utf-8")
        with self.assertRaisesRegex(quality.QualityError, "version artifact hash mismatch"):
            quality.load_treatment_run(self.project, run_id, require_closed=True)

    def test_p1_treatment_run_binds_two_pass_selection_before_stage(self) -> None:
        pass_a_body, txn = self.write_p1_chapter_inputs(1, 1)
        pass_b_body = self.project / "草稿/待验收/第001章_声线恢复.md"
        pass_b_body.write_text(body_text(1, 2), encoding="utf-8")
        beats = [
            {
                "scene_id": f"scene-{index}", "source_scene_id": f"scene-{index}", "scene_index": index,
                "actor": "甲", "goal": "完成当前决定", "known_basis": "甲已看到当前证据",
                "cause_or_trigger": "前一行动产生了明确结果", "action_or_choice": f"甲执行第{index}拍",
                "result": "行动产生可见后果",
            }
            for index in range(1, 5)
        ]
        start = {
            "schema": quality.TREATMENT_RUN_SCHEMA,
            "run_id": "treatment-001",
            "chapter": 1,
            "treatment": "P1",
            "treatment_version": "p1-causal-two-pass-v1",
            "common_base": treatment_common_base(),
            "budget": {"pass_a_attempts": 1, "pass_b_attempts": 1, "max_visible_chars": 5000},
            "stop_rule": "one-targeted-repair-then-fallback",
            "premise_interest_pre_read": {"status": "not_collected", "reason": "engineering shadow smoke"},
            "causal_beats": beats,
        }
        resampled_start = copy.deepcopy(start)
        resampled_start["run_id"] = "treatment-hidden-resample"
        resampled_start["budget"]["pass_a_attempts"] = 2
        with self.assertRaisesRegex(quality.QualityError, "at most 1"):
            quality.open_treatment_run(self.project, self.write_json("treatment-hidden-resample.json", resampled_start))
        resampled_b = copy.deepcopy(start)
        resampled_b["run_id"] = "treatment-hidden-resample-b"
        resampled_b["budget"]["pass_b_attempts"] = 2
        with self.assertRaisesRegex(quality.QualityError, "at most 1"):
            quality.open_treatment_run(self.project, self.write_json("treatment-hidden-resample-b.json", resampled_b))
        open_input = self.write_json("treatment-open.json", start)
        opened = self.run_cli(
            "open-treatment-run", "--project", self.project, "--input", open_input,
        )
        self.assertEqual((opened["status"], opened["mode"]), ("treatment_run_opened", "SHADOW"))

        pass_checks = {
            "causal_spine": True, "current_action_clear": True, "scene_grounded": True,
            "pov_stable": True, "characters_distinct": True,
            "explanation_bloat": False, "voice_loss": False,
        }
        pass_a = {
            "writer_run_id": "treatment-writer-a", "generation_attempts": 1,
            "body_sha256": quality.sha_file(pass_a_body), "evaluator_run_id": "treatment-evaluator-a",
            "evidence_anchors": ["场景1：行动与结果相邻。"], "checks": pass_checks,
        }
        pass_b = {
            "writer_run_id": "treatment-writer-b", "generation_attempts": 1,
            "body_sha256": quality.sha_file(pass_b_body), "evaluator_run_id": "treatment-evaluator-b",
            "source_pass_a_sha256": quality.sha_file(pass_a_body),
            "evidence_anchors": ["场景1：声线恢复但事实不变。"], "checks": pass_checks,
            "invariants": {
                "causal_beats_unchanged": True, "facts_unchanged": True,
                "event_order_unchanged": True, "pov_unchanged": True,
                "reader_oracle_unchanged": True,
            },
        }
        selector_input = {
            "items": [
                {"label": "A", "body_sha256": quality.sha_file(pass_a_body)},
                {"label": "B", "body_sha256": quality.sha_file(pass_b_body)},
            ],
            "pass_a_checks_sha256": quality.sha_json(pass_a),
            "pass_b_checks_sha256": quality.sha_json(pass_b),
        }
        close = {
            "schema": quality.TREATMENT_RUN_SCHEMA, "run_id": "treatment-001",
            "treatment": "P1",
            "pass_a": pass_a, "pass_b": pass_b,
            "selection": {
                "labels_hidden": True, "order_randomized": True, "winner": "B",
                "selector_run_id": "treatment-selector", "randomization_nonce": "nonce-001",
                "rationale": "B 保留清晰度且人物声线更可辨。",
                "input_fingerprint": quality.sha_json(selector_input),
            },
        }
        same_writer = copy.deepcopy(close)
        same_writer["pass_b"]["writer_run_id"] = same_writer["pass_a"]["writer_run_id"]
        same_writer["selection"]["input_fingerprint"] = quality.sha_json({
            **selector_input,
            "pass_b_checks_sha256": quality.sha_json(same_writer["pass_b"]),
        })
        with self.assertRaisesRegex(quality.QualityError, "writers must use isolated runs"):
            quality.close_treatment_run(
                self.project, "treatment-001", self.write_json("treatment-close-same-writer.json", same_writer),
                pass_a_body=pass_a_body, pass_b_body=pass_b_body,
            )
        reused_role = copy.deepcopy(close)
        reused_role["pass_b"]["writer_run_id"] = reused_role["pass_a"]["evaluator_run_id"]
        reused_role["selection"]["input_fingerprint"] = quality.sha_json({
            **selector_input,
            "pass_b_checks_sha256": quality.sha_json(reused_role["pass_b"]),
        })
        with self.assertRaisesRegex(quality.QualityError, "mutually isolated runs"):
            quality.close_treatment_run(
                self.project, "treatment-001", self.write_json("treatment-close-reused-role.json", reused_role),
                pass_a_body=pass_a_body, pass_b_body=pass_b_body,
            )
        reused_selector = copy.deepcopy(close)
        reused_selector["selection"]["selector_run_id"] = reused_selector["pass_a"]["writer_run_id"]
        with self.assertRaisesRegex(quality.QualityError, "selector must be isolated"):
            quality.close_treatment_run(
                self.project, "treatment-001", self.write_json("treatment-close-reused-selector.json", reused_selector),
                pass_a_body=pass_a_body, pass_b_body=pass_b_body,
            )
        extra_attempt = copy.deepcopy(close)
        extra_attempt["pass_b"]["generation_attempts"] = 2
        extra_attempt["selection"]["input_fingerprint"] = quality.sha_json({
            **selector_input,
            "pass_b_checks_sha256": quality.sha_json(extra_attempt["pass_b"]),
        })
        with self.assertRaisesRegex(quality.QualityError, "exactly one generation attempt"):
            quality.close_treatment_run(
                self.project, "treatment-001", self.write_json("treatment-close-extra-attempt.json", extra_attempt),
                pass_a_body=pass_a_body, pass_b_body=pass_b_body,
            )
        wrong_source = copy.deepcopy(close)
        wrong_source["pass_b"]["source_pass_a_sha256"] = quality.sha_bytes(b"wrong-A")
        wrong_source["selection"]["input_fingerprint"] = quality.sha_json({
            **selector_input,
            "pass_b_checks_sha256": quality.sha_json(wrong_source["pass_b"]),
        })
        with self.assertRaisesRegex(quality.QualityError, "bind the frozen Pass A body"):
            quality.close_treatment_run(
                self.project, "treatment-001", self.write_json("treatment-close-wrong-source.json", wrong_source),
                pass_a_body=pass_a_body, pass_b_body=pass_b_body,
            )
        oversized_a = self.project / "草稿/待验收/第001章_A超预算.md"
        oversized_b = self.project / "草稿/待验收/第001章_B超预算.md"
        oversized_a.write_text("# 第1章 A超预算\n" + "字" * 5100, encoding="utf-8")
        oversized_b.write_text("# 第1章 B超预算\n" + "字" * 5100, encoding="utf-8")
        oversized_close = copy.deepcopy(close)
        oversized_close["pass_a"]["body_sha256"] = quality.sha_file(oversized_a)
        oversized_close["pass_b"]["body_sha256"] = quality.sha_file(oversized_b)
        oversized_close["pass_b"]["source_pass_a_sha256"] = quality.sha_file(oversized_a)
        oversized_close["selection"]["input_fingerprint"] = quality.sha_json({
            "items": [
                {"label": "A", "body_sha256": quality.sha_file(oversized_a)},
                {"label": "B", "body_sha256": quality.sha_file(oversized_b)},
            ],
            "pass_a_checks_sha256": quality.sha_json(oversized_close["pass_a"]),
            "pass_b_checks_sha256": quality.sha_json(oversized_close["pass_b"]),
        })
        with self.assertRaisesRegex(quality.QualityError, "exceeds the frozen visible-character budget"):
            quality.close_treatment_run(
                self.project, "treatment-001", self.write_json("treatment-close-oversized.json", oversized_close),
                pass_a_body=oversized_a, pass_b_body=oversized_b,
            )
        close_input = self.write_json("treatment-close.json", close)
        closed = self.run_cli(
            "close-treatment-run", "--project", self.project, "--run", "treatment-001",
            "--input", close_input, "--pass-a-body", pass_a_body, "--pass-b-body", pass_b_body,
        )
        self.assertTrue(closed["non_enforced"])
        with self.assertRaisesRegex(quality.QualityError, "selected body"):
            quality.stage(
                self.project, 1, pass_a_body, txn, kind="draft", resolution="within_user_band",
                metadata={"treatment_run_id": "treatment-001"},
            )
        staged = self.run_cli(
            "stage", "--project", self.project, "--chapter", 1,
            "--candidate", pass_b_body, "--tracking-input", txn, "--kind", "draft",
            "--metadata", json.dumps({"treatment_run_id": "treatment-001"}),
        )
        self.assertEqual(staged["treatment_run_id"], "treatment-001")
        self.assertEqual(staged["revision"], closed["selected_body_sha256"])
        packet = self.p1_packet(staged, delivered=True)
        review_path = self.write_json("treatment-selected-review.json", packet)
        self.run_cli("certify", "--project", self.project, "--pending", staged["pending_id"], "--input", review_path)
        self.run_cli("accept", "--project", self.project, "--pending", staged["pending_id"])
        provenance = quality.manifest_for(self.project)["chapters"]["1"]["treatment_provenance"]
        self.assertEqual(provenance, {
            "treatment": "P1",
            "run_id": "treatment-001",
            "start_boundary_sha256": opened["start_boundary_sha256"],
            "close_boundary_sha256": closed["close_boundary_sha256"],
        })
        artifact = self.project / ".story-quality/treatment-runs/treatment-001/artifacts/pass-b.md"
        artifact.write_text("tampered treatment body", encoding="utf-8")
        with self.assertRaisesRegex(quality.QualityError, "artifact hash mismatch"):
            quality.load_treatment_run(self.project, "treatment-001", require_closed=True)

    def test_p1_lifecycle_parser_rejects_scene_catalog_table_mismatch(self) -> None:
        self.write_p1_chapter_inputs(1, 1)
        outline = self.project / "大纲/细纲_第001章.md"
        text = outline.read_text(encoding="utf-8")
        text = text.replace('| 4 | 决定产生可见后果 | 结果 | 不新增支线 |\n', '')
        outline.write_text(text, encoding="utf-8")
        with self.assertRaisesRegex(quality.QualityError, "exactly match"):
            quality.outline_contract(outline)

    def test_p1_thresholds_use_directional_reader_story_quantiles(self) -> None:
        def rows(story: str, value: float) -> list[dict[str, object]]:
            return [
                {
                    "story_package_id": story, "chapter": chapter,
                    "observed_first_friction_ratio": value,
                    "observed_friction_severity": int(round(1 + value * 3)),
                    "observed_read_on_intensity": int(round(1 + value * 4)),
                    "observed_emotion_intensity": int(round(value * 5)),
                    "observed_confidence": value,
                }
                for chapter in range(1, 16)
            ]

        readers = []
        for index, (story_a, story_b) in enumerate(((0.1, 0.9), (0.9, 0.9)), 1):
            raw = {"chapter_measurements": {"story-a": rows("story-a", story_a), "story-b": rows("story-b", story_b)}}
            readers.append({"reader_id": f"Q{index}", "raw_observations": raw})
        derived = quality.derive_thresholds_from_human_import(
            {"readers": readers}, 2, threshold_spec(),
        )
        # story-a median=.5, story-b median=.9, then stories receive equal weight.
        self.assertEqual(derived["early_friction_ratio"], 0.7)
        self.assertEqual(derived["minimum_confidence"], 0.7)
        self.assertGreater(derived["minimum_read_on_intensity"], 1)
        self.assertEqual(derived["corroborated_quit_readers"], 2)

    def test_reader_v3_preserves_natural_quit_during_study_continuation(self) -> None:
        row = reader_v2(
            "study-reader", None, chapter=4, revision=quality.sha_bytes(b"chapter-4"),
            input_fingerprint=quality.sha_bytes(b"reader-input"), expectation_id="EX-01-004",
        )
        row["measurements"].update({
            "first_quit_chapter": 3,
            "continued_by_choice": False,
            "continued_for_study": True,
            "cumulative_confusion": {"level": 3, "delta": 1, "reason": "连续两章不知道人物为何行动。"},
            "mystery_fatigue": {"level": 2, "delta": 1, "reason": "开放问题增加但没有当前锚点。"},
        })
        measurements = quality.validate_reader_measurements(row)
        self.assertEqual(measurements["first_quit_chapter"], 3)
        self.assertFalse(measurements["continued_by_choice"])
        self.assertTrue(measurements["continued_for_study"])
        bad = copy.deepcopy(row)
        bad["measurements"]["continued_by_choice"] = True
        with self.assertRaisesRegex(quality.QualityError, "natural continuation"):
            quality.validate_reader_measurements(bad)
        previous = copy.deepcopy(measurements)
        previous.update({
            "first_quit_chapter": 3,
            "cumulative_confusion": {"level": 2, "delta": 1, "reason": "上一章开始混乱。"},
            "mystery_fatigue": {"level": 1, "delta": 1, "reason": "上一章开始疲劳。"},
        })
        quality.validate_reader_measurement_transition(previous, measurements, 4)
        erased = copy.deepcopy(measurements)
        erased["first_quit_chapter"] = None
        erased["continued_for_study"] = False
        with self.assertRaisesRegex(quality.QualityError, "immutable once recorded"):
            quality.validate_reader_measurement_transition(previous, erased, 4)

    def test_suspense_debt_is_derived_for_a_nonempty_open_question(self) -> None:
        manifest = {
            "event_index": {
                "OPEN-1": {
                    "id": "OPEN-1", "chapter": 2, "kind": "open_question",
                    "data": {"open_id": "Q-door", "state": "open", "planned_payoff_chapter": 7},
                },
                "OPEN-2": {
                    "id": "OPEN-2", "chapter": 4, "kind": "open_question",
                    "data": {"open_id": "Q-name", "state": "paused", "planned_payoff_chapter": None},
                },
            },
        }
        debt = quality.derive_suspense_debt(manifest, 5)
        self.assertEqual([row["open_id"] for row in debt], ["Q-door", "Q-name"])
        self.assertEqual(debt[0]["age"], 3)
        self.assertEqual(debt[1]["state"], "paused")

    def p1_packet(self, staged: dict[str, object], *, delivered: bool, kind: str = "draft", parent: str | None = None) -> dict[str, object]:
        chapter = int(staged["chapter"])
        base = quality.manifest_for(self.project)
        previous = {reader_id: chain.get(str(chapter - 1)) for reader_id, chain in base.get("reader_chains", {}).items()}
        packet = review_packet(
            chapter, str(staged["revision"]), previous, kind=kind, parent=parent,
            base=base, outline_sha256=str(staged["outline_sha256"]),
        )
        input_fingerprint = quality.reader_input_fingerprint(base, staged)
        cohort = [
            reader_v2(
                f"core-{index}", previous.get(f"core-{index}"), chapter=chapter,
                revision=str(staged["revision"]), input_fingerprint=input_fingerprint,
                expectation_id=f"EX-01-{chapter:03d}", delivered=delivered,
            )
            for index in (1, 2)
        ]
        packet["reader_evidence"]["cohort"] = cohort
        state_hashes = []
        for row in cohort:
            normalized = copy.deepcopy(row)
            normalized["chapter"] = chapter
            normalized.pop("state_hash", None)
            state_hashes.append(quality.sha_json(normalized))
        packet["reader_evidence"]["judge"]["input_fingerprint"] = quality.sha_json({
            "outline_sha256": staged["outline_sha256"], "reader_state_hashes": state_hashes,
        })
        packet["outline_contract"] = copy.deepcopy(staged["outline_contract"])
        derived = quality.derive_strength_gate(staged, staged["quality_policy"], cohort)
        packet["strength_gate"] = {**derived, "derived": True}
        return packet

    def stage_certify_accept(
        self,
        chapter: int,
        variant: int,
        *,
        kind: str = "draft",
        mode: str = "append",
        treatment_run_id: str | None = None,
    ) -> dict[str, object]:
        candidate, txn = self.write_chapter_inputs(chapter, variant, mode=mode)
        base = quality.manifest_for(self.project)
        parent = base["chapters"].get(str(chapter), {}).get("revision")
        metadata = {}
        if kind == "revision":
            metadata = {"finding_ids": ["LOGIC-1"], "impact_regions": ["选择到后果"], "repair_scope": "local"}
        if treatment_run_id is not None:
            metadata["treatment_run_id"] = treatment_run_id
        staged = quality.stage(self.project, chapter, candidate, txn, kind=kind, resolution="within_user_band", metadata=metadata)
        previous = {reader_id: chain.get(str(chapter - 1)) for reader_id, chain in base.get("reader_chains", {}).items()}
        packet = review_packet(
            chapter,
            staged["revision"],
            previous,
            kind=kind,
            parent=parent,
            base=base,
            outline_sha256=staged["outline_sha256"],
            finding_ids=metadata.get("finding_ids"),
        )
        if chapter % 15 == 0:
            fingerprint = quality.reader_input_fingerprint(base, staged)
            revisions = quality.reader_revision_sequence(base, staged)
            fresh = reader(
                f"fresh-reader-{chapter}", None,
                chapter=chapter, revision=staged["revision"], input_fingerprint=fingerprint,
            )
            fresh.update({
                "cohort_type": "fresh_replay",
                "replayed_from_chapter": 1,
                "replayed_through_chapter": chapter,
                "replayed_revision_hashes": revisions,
                "batch_hashes": quality.reader_batch_hashes(revisions),
            })
            packet["reader_evidence"]["cohort"].append(fresh)
            state_hashes = []
            for row in packet["reader_evidence"]["cohort"]:
                normalized = copy.deepcopy(row)
                normalized["chapter"] = chapter
                normalized.pop("state_hash", None)
                state_hashes.append(quality.sha_json(normalized))
            packet["reader_evidence"]["judge"]["input_fingerprint"] = quality.sha_json({
                "outline_sha256": staged["outline_sha256"],
                "reader_state_hashes": state_hashes,
            })
        packet_path = self.write_json(f"review-{chapter}-{variant}.json", packet)
        certified = quality.certify(self.project, staged["pending_id"], packet_path)
        self.assertTrue(certified["eligible"])
        return quality.accept(self.project, staged["pending_id"])

    def test_cli_temporary_project_accepts_one_chapter_end_to_end(self) -> None:
        project = self.root / "cli-book"
        project.mkdir()
        (project / "大纲").mkdir()
        (project / "正文").mkdir()
        (project / "草稿/待验收").mkdir(parents=True)
        tracking.initialize(project, initial())

        initialized = self.run_cli("init", "--project", project)
        self.assertEqual(initialized["status"], "initialized")

        chapter = 1
        (project / "大纲/细纲_第001章.md").write_text(
            "- 字数目标：1000 字\n- 字数口径：visible_chars_v1\n"
            "- 结尾拍ID/类型：EB-01-001；choice；作出决定\n"
            "- 期待ID/类型：EX-01-001；aftermath；决定的后果\n"
            "- 读者验收预期：must_know=[决定发生]；may_believe=[]；must_not_know=[幕后原因]；open_ids=[EX-01-001]\n"
            "| # | 情节点（谁做了什么） | 功能标签 | 执行边界 |\n"
            "|---|---|---|---|\n| 1 | 甲作出决定 | 推进 | 不新增支线 |\n",
            encoding="utf-8",
        )
        candidate = project / "草稿/待验收/第001章_命令行验收.md"
        candidate.write_text(body_text(chapter, 9), encoding="utf-8")
        transaction_path = self.write_json("cli-transaction.json", transaction(chapter, 0))

        staged = self.run_cli(
            "stage", "--project", project, "--chapter", chapter,
            "--candidate", candidate, "--tracking-input", transaction_path,
            "--kind", "draft",
        )
        self.assertEqual(staged["status"], "staged")

        base = quality.manifest_for(project)
        packet = review_packet(
            chapter,
            str(staged["revision"]),
            {"reader-1": None, "reader-2": None},
            base=base,
            outline_sha256=str(staged["outline_sha256"]),
        )
        review_path = self.write_json("cli-review.json", packet)
        certified = self.run_cli(
            "certify", "--project", project,
            "--pending", staged["pending_id"], "--input", review_path,
        )
        self.assertTrue(certified["eligible"])

        accepted = self.run_cli("accept", "--project", project, "--pending", staged["pending_id"])
        self.assertEqual(accepted["status"], "accepted")
        checked = self.run_cli("check", "--project", project)
        self.assertEqual(checked["status"], "pass")
        self.assertEqual(len(list((project / "正文").glob("第001章_*.md"))), 1)
        self.assertEqual(json.loads((project / ".story-quality/HEAD.json").read_text(encoding="utf-8"))["generation_id"], checked["generation_id"])

    def test_atomic_accept_graph_and_projection_check(self) -> None:
        accepted = self.stage_certify_accept(1, 1)
        self.assertEqual(accepted["status"], "accepted")
        checked = quality.check(self.project)
        self.assertEqual(checked["status"], "pass")
        self.assertEqual(len(list((self.project / "正文").glob("第001章_*.md"))), 1)
        graph = quality.graph(self.project)
        self.assertEqual(graph["nodes"], ["乙", "甲"])
        self.assertEqual(graph["relations"][0]["after"], "合作1")
        self.assertEqual(graph["character_arcs"][0]["dimension"], "担当")
        dependencies = self.write_json(
            "accepted-dependencies.json",
            {"characters": ["甲"], "event_ids": [], "kinds": ["relation", "arc"]},
        )
        hot = quality.hot_context(self.project, dependencies)
        self.assertTrue(hot["bounded"])
        self.assertEqual({event["kind"] for event in hot["events"]}, {"relation", "arc"})
        with self.assertRaisesRegex(tracking.TrackingError, "quality lifecycle is initialized"):
            tracking.apply_transaction(self.project, transaction(2, 1))

        rogue_body = self.project / "正文/第002章_未验收.md"
        rogue_body.write_text("# 未验收\n不能进入正文", encoding="utf-8")
        rogue_tracking = self.project / "追踪/rogue.md"
        rogue_tracking.write_text("不属于接受代际", encoding="utf-8")
        with self.assertRaisesRegex(quality.QualityError, "unaccepted|extra"):
            quality.check(self.project)
        candidate, txn = self.write_chapter_inputs(2, 1)
        with self.assertRaisesRegex(quality.QualityError, "unaccepted|extra"):
            quality.stage(self.project, 2, candidate, txn, kind="draft", resolution="within_user_band", metadata={})
        rebuilt = quality.rebuild(self.project)
        self.assertEqual(rebuilt["status"], "rebuilt")
        self.assertFalse(rogue_body.exists())
        self.assertFalse(rogue_tracking.exists())
        self.assertTrue(any((self.project / ".story-quality/recovered-projections").rglob("第002章_未验收.md")))
        self.assertEqual(quality.check(self.project)["status"], "pass")

        manifest = quality.manifest_for(self.project)
        entry = manifest["chapters"]["1"]
        _, metadata = quality.revision_paths(quality.quality_root(self.project), 1, entry["revision"])
        original = metadata.read_bytes()
        metadata.write_bytes(original + b" ")
        with self.assertRaisesRegex(quality.QualityError, "metadata hash mismatch"):
            quality.check(self.project)
        metadata.write_bytes(original)
        self.assertEqual(quality.check(self.project)["status"], "pass")

        outside = self.root / "outside-body-projection"
        outside.mkdir()
        shutil.rmtree(self.project / "正文")
        (self.project / "正文").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(quality.QualityError, "symbolic-link"):
            quality.rebuild(self.project)
        (self.project / "正文").unlink()
        (self.project / "正文").mkdir()
        self.assertEqual(quality.rebuild(self.project)["status"], "rebuilt")
        self.assertEqual(quality.check(self.project)["status"], "pass")

    def test_blind_tie_keeps_previous_revision(self) -> None:
        self.stage_certify_accept(1, 1)
        candidate, txn = self.write_chapter_inputs(1, 2, mode="revision")
        base = quality.manifest_for(self.project)
        parent = base["chapters"]["1"]["revision"]
        staged = quality.stage(
            self.project, 1, candidate, txn, kind="revision", resolution="within_user_band",
            metadata={"finding_ids": ["PROSE-9"], "impact_regions": ["末段"], "repair_scope": "local"},
        )
        packet = review_packet(
            1,
            staged["revision"],
            {"reader-1": None, "reader-2": None},
            kind="revision",
            parent=parent,
            winner="tie",
            base=base,
            outline_sha256=staged["outline_sha256"],
            finding_ids=["PROSE-9"],
        )
        certified = quality.certify(self.project, staged["pending_id"], self.write_json("tie.json", packet))
        self.assertFalse(certified["eligible"])
        self.assertEqual(certified["selection_status"], "FIX_FAILED")
        with self.assertRaisesRegex(quality.QualityError, "previous version"):
            quality.accept(self.project, staged["pending_id"])
        self.assertEqual(quality.manifest_for(self.project)["chapters"]["1"]["revision"], parent)

    def test_old_chapter_revision_invalidates_then_replays_downstream(self) -> None:
        self.stage_certify_accept(1, 1)
        self.stage_certify_accept(2, 1)
        revised = self.stage_certify_accept(1, 3, kind="revision", mode="revision")
        self.assertEqual(revised["status"], "accepted_replay_required")
        self.assertEqual(revised["stale"]["reader_from"], 2)
        self.assertEqual(quality.check(self.project)["status"], "replay_required")
        with self.assertRaisesRegex(quality.QualityError, "requires sequential replay"):
            quality.graph(self.project)
        candidate, txn = self.write_chapter_inputs(3, 1)
        with self.assertRaisesRegex(quality.QualityError, "requires sequential replay"):
            quality.stage(self.project, 3, candidate, txn, kind="draft", resolution="within_user_band", metadata={})
        dependencies = self.write_json("dependencies.json", {"characters": ["甲"], "event_ids": [], "kinds": ["relation", "arc"]})
        with self.assertRaisesRegex(quality.QualityError, "requires sequential replay"):
            quality.hot_context(self.project, dependencies)

        base = quality.manifest_for(self.project)
        previous = {reader_id: chain["1"] for reader_id, chain in base["reader_chains"].items()}
        chapter_two = base["chapters"]["2"]
        packet = review_packet(2, chapter_two["revision"], previous, kind="replay", base=base, outline_sha256=quality.sha_file(self.project / "大纲/细纲_第002章.md"))
        replay_input = self.write_json("replay.json", {"schema": quality.REPLAY_SCHEMA, "packets": [packet]})
        replayed = quality.replay(self.project, replay_input)
        self.assertEqual(replayed["status"], "replayed")
        self.assertEqual(quality.check(self.project)["status"], "pass")

    def test_malformed_derived_index_cannot_advance_head_on_failed_accept(self) -> None:
        for chapter in range(1, 4):
            self.stage_certify_accept(chapter, 10 + chapter)
        candidate, txn = self.write_chapter_inputs(1, 19, mode="revision")
        base = quality.manifest_for(self.project)
        parent = base["chapters"]["1"]["revision"]
        metadata = {"finding_ids": ["LOGIC-1"], "impact_regions": ["选择到后果"], "repair_scope": "local"}
        staged = quality.stage(
            self.project, 1, candidate, txn, kind="revision", resolution="within_user_band", metadata=metadata,
        )
        packet = review_packet(
            1, staged["revision"], {"reader-1": None, "reader-2": None}, kind="revision",
            parent=parent, base=base, outline_sha256=staged["outline_sha256"], finding_ids=metadata["finding_ids"],
        )
        quality.certify(self.project, staged["pending_id"], self.write_json("malformed-index-review.json", packet))
        index_path = self.project / ".story-quality/CHECKPOINT_INDEX.json"
        index_path.write_text("{bad", encoding="utf-8")
        head_before = quality.head_record(self.project)["generation_id"]
        with self.assertRaisesRegex(quality.QualityError, "unable to read derived quality index"):
            quality.accept(self.project, staged["pending_id"])
        self.assertEqual(quality.head_record(self.project)["generation_id"], head_before)
        quality.atomic_json(
            index_path,
            {"schema": quality.CHECKPOINT_SCHEMA, "entries": [{"chapter": 3, "status": "fresh"}]},
        )
        accepted = quality.accept(self.project, staged["pending_id"])
        index = json.loads(index_path.read_text(encoding="utf-8"))
        self.assertEqual(index["entries"][0]["status"], "stale")
        self.assertEqual(index["entries"][0]["invalidated_by_generation"], accepted["generation_id"])

    def test_failed_perspective_cannot_be_accepted(self) -> None:
        candidate, txn = self.write_chapter_inputs(1, 1)
        base = quality.manifest_for(self.project)
        staged = quality.stage(self.project, 1, candidate, txn, kind="draft", resolution="within_user_band", metadata={})
        packet = review_packet(1, staged["revision"], {"reader-1": None, "reader-2": None}, base=base, outline_sha256=staged["outline_sha256"])
        packet["perspectives"]["reader-comprehension"]["verdict"] = "FAIL"
        certified = quality.certify(self.project, staged["pending_id"], self.write_json("failed-view.json", packet))
        self.assertFalse(certified["eligible"])
        certificate = json.loads(
            (self.project / ".story-quality/pending" / staged["pending_id"] / "certificate.json").read_text(encoding="utf-8")
        )
        self.assertEqual(certificate["packet"]["correctness_gate"]["present_action"], "FAIL")
        self.assertEqual(certificate["packet"]["correctness_gate"]["mystery_legitimacy"], "FAIL")
        with self.assertRaisesRegex(quality.QualityError, "cannot be accepted"):
            quality.accept(self.project, staged["pending_id"])

    def test_p1_flat_cannot_mask_a_p0_correctness_failure(self) -> None:
        calibration = self.install_heldout_calibration("heldout-p0-precedence")
        quality.configure_policy(
            self.project,
            self.write_json("p0-precedence-policy.json", enforce_policy(calibration, activated_from_chapter=1)),
        )
        candidate, txn = self.write_p1_chapter_inputs(1, 2)
        staged = quality.stage(self.project, 1, candidate, txn, kind="draft", resolution="within_user_band", metadata={})
        packet = self.p1_packet(staged, delivered=False)
        packet["perspectives"]["reader-comprehension"]["verdict"] = "FAIL"
        result = quality.certify(
            self.project,
            staged["pending_id"],
            self.write_json("p0-precedence-review.json", packet),
        )
        self.assertEqual((result["strength_status"], result["selection_status"]), ("FLAT", "REJECTED"))
        certificate = json.loads(
            (self.project / ".story-quality/pending" / staged["pending_id"] / "certificate.json").read_text(encoding="utf-8")
        )
        self.assertFalse(certificate["p0_eligible_before_strength"])
        request = {
            "schema": quality.REOPEN_SCHEMA,
            "pending_id": staged["pending_id"],
            "level": "L2",
            "simulation_only": False,
            "localized_regions": [],
            "author_authorization": "作者批准重开。",
            "search_scope": {"allowed": ["opening"]},
            "reason_codes": certificate["packet"]["strength_gate"]["reason_codes"],
        }
        with self.assertRaisesRegex(quality.QualityError, "P0-eligible"):
            quality.open_reopen_case(self.project, self.write_json("p0-precedence-reopen.json", request))

    def test_legacy_tracking_fingerprint_and_pre_activation_policy_remain_compatible(self) -> None:
        legacy_event = {
            "id": "E001",
            "story_time": "第一天",
            "objective_fact": "甲作出决定",
            "reader_knowledge": "读者知道甲已决定",
            "reveal_status": "shown",
            "reveal_chapter": 1,
            "characters": ["甲"],
        }
        self.assertEqual(
            quality.tracking_event_fingerprint(legacy_event),
            quality.sha_json(legacy_event),
        )
        self.stage_certify_accept(1, 3)
        calibration = self.install_heldout_calibration("heldout-activation")
        configured = quality.configure_policy(
            self.project,
            self.write_json("activation-policy.json", enforce_policy(calibration, activated_from_chapter=3)),
        )
        old_policy, old_hash = quality.effective_policy(self.project, 1)
        new_policy, new_hash = quality.effective_policy(self.project, 3)
        self.assertEqual(old_policy["strength_mode"], "SHADOW")
        self.assertEqual(new_policy["strength_mode"], "ENFORCE")
        self.assertNotEqual(old_hash, new_hash)
        self.assertEqual(new_hash, configured["policy_sha256"])
        self.assertTrue((self.project / ".story-quality/policies" / f"{old_hash}.json").is_file())

        self.stage_certify_accept(2, 4)
        legacy_head = quality.head_record(self.project)
        legacy_manifest_path = self.project / ".story-quality/generations" / legacy_head["generation_id"] / "manifest.json"
        legacy_manifest = json.loads(legacy_manifest_path.read_text(encoding="utf-8"))
        legacy_manifest["quality_certificates"]["2"].pop("quality_policy_sha256")
        quality.atomic_json(legacy_manifest_path, legacy_manifest)
        quality.atomic_json(
            self.project / ".story-quality/HEAD.json",
            {"schema": quality.SCHEMA, "generation_id": legacy_head["generation_id"], "manifest_sha256": quality.sha_file(legacy_manifest_path)},
        )
        revised = self.stage_certify_accept(1, 5, kind="revision", mode="revision")
        self.assertEqual(revised["status"], "accepted_replay_required")
        base = quality.manifest_for(self.project)
        previous = {reader_id: chain["1"] for reader_id, chain in base["reader_chains"].items()}
        chapter_two = base["chapters"]["2"]
        packet = review_packet(
            2,
            chapter_two["revision"],
            previous,
            kind="replay",
            base=base,
            outline_sha256=quality.sha_file(self.project / "大纲/细纲_第002章.md"),
        )
        replayed = quality.replay(
            self.project,
            self.write_json("pre-activation-replay.json", {"schema": quality.REPLAY_SCHEMA, "packets": [packet]}),
        )
        self.assertEqual(replayed["status"], "replayed")
        replay_manifest = quality.manifest_for(self.project)
        replay_policy_hash = replay_manifest["quality_certificates"]["2"]["quality_policy_sha256"]
        self.assertTrue((self.project / ".story-quality/policies" / f"{replay_policy_hash}.json").is_file())

        second_revision = self.stage_certify_accept(1, 6, kind="revision", mode="revision")
        self.assertEqual(second_revision["status"], "accepted_replay_required")
        base = quality.manifest_for(self.project)
        previous = {reader_id: chain["1"] for reader_id, chain in base["reader_chains"].items()}
        chapter_two = base["chapters"]["2"]
        second_packet = review_packet(
            2, chapter_two["revision"], previous, kind="replay", base=base,
            outline_sha256=quality.sha_file(self.project / "大纲/细纲_第002章.md"),
        )
        second_replay = quality.replay(
            self.project,
            self.write_json("second-pre-activation-replay.json", {"schema": quality.REPLAY_SCHEMA, "packets": [second_packet]}),
        )
        self.assertEqual(second_replay["status"], "replayed")

    def test_reader_path_escape_and_ghost_corroboration_are_rejected(self) -> None:
        candidate, txn = self.write_chapter_inputs(1, 1)
        base = quality.manifest_for(self.project)
        staged = quality.stage(self.project, 1, candidate, txn, kind="draft", resolution="within_user_band", metadata={})
        packet = review_packet(1, staged["revision"], {"reader-1": None, "reader-2": None}, base=base, outline_sha256=staged["outline_sha256"])
        packet["reader_evidence"]["cohort"][0]["reader_id"] = "../../escaped"
        with self.assertRaisesRegex(quality.QualityError, "safe path component"):
            quality.certify(self.project, staged["pending_id"], self.write_json("escape.json", packet))

        packet = review_packet(1, staged["revision"], {"reader-1": None, "reader-2": None}, base=base, outline_sha256=staged["outline_sha256"])
        for row in packet["reader_evidence"]["cohort"]:
            row["retention_verdict"] = "block"
            row["retention_issue_ids"] = ["fatigue-1"]
        packet["reader_evidence"].update({
            "retention_decision": "block",
            "corroborated_reader_ids": ["ghost-a", "ghost-b"],
            "corroborating_evidence": "两份报告同向。",
        })
        with self.assertRaisesRegex(quality.QualityError, "outside the reviewed cohort"):
            quality.certify(self.project, staged["pending_id"], self.write_json("ghost.json", packet))

    def test_benchmark_and_role_mutations_are_rejected(self) -> None:
        self.stage_certify_accept(1, 1)
        candidate, txn = self.write_chapter_inputs(1, 2, mode="revision")
        base = quality.manifest_for(self.project)
        parent = base["chapters"]["1"]["revision"]
        staged = quality.stage(
            self.project, 1, candidate, txn, kind="revision", resolution="within_user_band",
            metadata={"finding_ids": ["LOGIC-1"], "impact_regions": ["选择"], "repair_scope": "local"},
        )
        packet = review_packet(1, staged["revision"], {"reader-1": None, "reader-2": None}, kind="revision", parent=parent, base=base, outline_sha256=staged["outline_sha256"])
        packet["roles"]["repairer"] = packet["roles"]["defect_evaluator"]
        with self.assertRaisesRegex(quality.QualityError, "repairer must be isolated"):
            quality.certify(self.project, staged["pending_id"], self.write_json("role-reuse.json", packet))

        packet = review_packet(1, staged["revision"], {"reader-1": None, "reader-2": None}, kind="revision", parent=parent, base=base, outline_sha256=staged["outline_sha256"])
        packet["perspectives"]["prose-style"]["execution"]["run_id"] = packet["perspectives"]["story-logic"]["execution"]["run_id"]
        with self.assertRaisesRegex(quality.QualityError, "globally distinct"):
            quality.certify(self.project, staged["pending_id"], self.write_json("perspective-run-reuse.json", packet))

        packet = review_packet(1, staged["revision"], {"reader-1": None, "reader-2": None}, kind="revision", parent=parent, base=base, outline_sha256=staged["outline_sha256"])
        benchmark = packet["selection_protocol"]["positive_benchmark"]
        benchmark["mutants"][0]["artifact_text"] = benchmark["controls"][0]["artifact_text"]
        benchmark["mutants"][0]["artifact_sha256"] = benchmark["controls"][0]["artifact_sha256"]
        with self.assertRaisesRegex(quality.QualityError, "differs from the frozen fixture"):
            quality.certify(self.project, staged["pending_id"], self.write_json("benchmark-overlap.json", packet))

        packet = review_packet(1, staged["revision"], {"reader-1": None, "reader-2": None}, kind="revision", parent=parent, base=base, outline_sha256=staged["outline_sha256"])
        packet["selection_protocol"]["positive_benchmark"]["held_out"][0]["artifact_text"] += " tampered"
        with self.assertRaisesRegex(quality.QualityError, "not bound to its text artifact"):
            quality.certify(self.project, staged["pending_id"], self.write_json("benchmark-body-mutation.json", packet))

        packet = review_packet(1, staged["revision"], {"reader-1": None, "reader-2": None}, kind="revision", parent=parent, base=base, outline_sha256=staged["outline_sha256"])
        packet["blind_ab"]["package"]["items"][0]["body_sha256"] = quality.sha_bytes(b"invented-body")
        with self.assertRaisesRegex(quality.QualityError, "previous and candidate bodies"):
            quality.certify(self.project, staged["pending_id"], self.write_json("blind-body-mutation.json", packet))

        packet = review_packet(1, staged["revision"], {"reader-1": None, "reader-2": None}, kind="revision", parent=parent, base=base, outline_sha256=staged["outline_sha256"])
        packet["selection_protocol"]["dialogue_test"]["voice_bearing_line_count"] = 1
        with self.assertRaisesRegex(quality.QualityError, "zero voice-bearing lines"):
            quality.certify(self.project, staged["pending_id"], self.write_json("dialogue-exemption-mutation.json", packet))

        packet = review_packet(1, staged["revision"], {"reader-1": None, "reader-2": None}, kind="revision", parent=parent, base=base, outline_sha256=staged["outline_sha256"])
        fake_line = "「这句台词不在候选正文里。」"
        packet["selection_protocol"]["dialogue_test"] = {
            "applicable": True,
            "scope": "voice-bearing-only",
            "blinded": True,
            "voice_card_provided": True,
            "prior_context_provided": True,
            "global_accuracy_threshold": False,
            "speaker_swap_diagnostic": True,
            "catchphrase_fix": False,
            "voice_bearing_line_count": 0,
            "samples": [{
                "line_text": fake_line,
                "line_sha256": quality.sha_bytes(fake_line.encode()),
                "expected_speaker": "甲",
                "predicted_speaker": "甲",
                "swapped_predicted_speaker": "乙",
                "speaker_swap_changed": True,
            }],
            "run_id": "dialogue-isolated-run",
            "input_fingerprint": quality.sha_json([{
                "line_text": fake_line,
                "line_sha256": quality.sha_bytes(fake_line.encode()),
                "expected_speaker": "甲",
                "predicted_speaker": "甲",
                "swapped_predicted_speaker": "乙",
                "speaker_swap_changed": True,
            }]),
        }
        with self.assertRaisesRegex(quality.QualityError, "detected voice-bearing line"):
            quality.certify(self.project, staged["pending_id"], self.write_json("dialogue-body-mutation.json", packet))

        packet = review_packet(1, staged["revision"], {"reader-1": None, "reader-2": None}, kind="revision", parent=parent, base=base, outline_sha256=staged["outline_sha256"])
        candidate_body, _ = quality.revision_paths(quality.quality_root(self.project), 1, staged["revision"])
        parent_body, _ = quality.revision_paths(quality.quality_root(self.project), 1, parent)
        repeated = {"body": parent_body.read_bytes().decode("utf-8"), "body_sha256": parent}
        candidate_versions = [
            {"body": candidate_body.read_bytes().decode("utf-8"), "body_sha256": staged["revision"]},
            {"body": "candidate alternate body", "body_sha256": quality.sha_bytes(b"candidate alternate body")},
        ]
        packet["selection_protocol"]["variants"] = {
            "premarked_key_chapter": True,
            "baseline_versions": [repeated, copy.deepcopy(repeated)],
            "candidate_versions": candidate_versions,
            "baseline_count": 2,
            "candidate_count": 2,
        }
        with self.assertRaisesRegex(quality.QualityError, "distinct within each arm"):
            quality.certify(self.project, staged["pending_id"], self.write_json("variant-mutation.json", packet))

        packet = review_packet(1, staged["revision"], {"reader-1": None, "reader-2": None}, kind="revision", parent=parent, base=base, outline_sha256=staged["outline_sha256"])
        baseline_alt = "baseline alternate body"
        candidate_alt = "candidate alternate body"
        packet["selection_protocol"]["variants"] = {
            "premarked_key_chapter": True,
            "baseline_versions": [
                {"body": parent_body.read_bytes().decode("utf-8"), "body_sha256": parent},
                {"body": baseline_alt + " tampered", "body_sha256": quality.sha_bytes(baseline_alt.encode())},
            ],
            "candidate_versions": [
                {"body": candidate_body.read_bytes().decode("utf-8"), "body_sha256": staged["revision"]},
                {"body": candidate_alt, "body_sha256": quality.sha_bytes(candidate_alt.encode())},
            ],
            "baseline_count": 2,
            "candidate_count": 2,
        }
        with self.assertRaisesRegex(quality.QualityError, "not bound to its text artifact"):
            quality.certify(self.project, staged["pending_id"], self.write_json("variant-body-mutation.json", packet))

        packet = review_packet(1, staged["revision"], {"reader-1": None, "reader-2": None}, kind="revision", parent=parent, base=base, outline_sha256=staged["outline_sha256"])
        packet["reader_evidence"]["cohort"][0]["run_id"] = packet["perspectives"]["story-logic"]["execution"]["run_id"]
        with self.assertRaisesRegex(quality.QualityError, "globally distinct"):
            quality.certify(self.project, staged["pending_id"], self.write_json("reader-run-reuse.json", packet))

        packet = review_packet(1, staged["revision"], {"reader-1": None, "reader-2": None}, kind="revision", parent=parent, base=base, outline_sha256=staged["outline_sha256"])
        packet["reader_evidence"]["judge"]["run_id"] = packet["reader_evidence"]["cohort"][0]["run_id"]
        with self.assertRaisesRegex(quality.QualityError, "globally distinct"):
            quality.certify(self.project, staged["pending_id"], self.write_json("judge-run-reuse.json", packet))

        packet = review_packet(1, staged["revision"], {"reader-1": None, "reader-2": None}, kind="revision", parent=parent, base=base, outline_sha256=staged["outline_sha256"])
        packet["reader_evidence"]["cohort"][0]["retention_verdict"] = "block"
        packet["reader_evidence"]["cohort"][0]["retention_issue_ids"] = ["logic-friction"]
        reader_hashes = []
        for row in packet["reader_evidence"]["cohort"]:
            normalized_reader = copy.deepcopy(row)
            normalized_reader["chapter"] = 1
            normalized_reader.pop("state_hash", None)
            reader_hashes.append(quality.sha_json(normalized_reader))
        packet["reader_evidence"]["judge"]["input_fingerprint"] = quality.sha_json({
            "outline_sha256": staged["outline_sha256"],
            "reader_state_hashes": reader_hashes,
        })
        single_concern = quality.certify(
            self.project, staged["pending_id"], self.write_json("retention-single-concern.json", packet)
        )
        self.assertTrue(single_concern["eligible"], "one subjective reader must not veto the chapter")

        packet = review_packet(1, staged["revision"], {"reader-1": None, "reader-2": None}, kind="revision", parent=parent, base=base, outline_sha256=staged["outline_sha256"])
        packet["posthoc_extraction"]["authoritative_events"][0]["tracking_event_fingerprint"] = quality.sha_bytes(b"contradictory-fact")
        with self.assertRaisesRegex(quality.QualityError, "contradicts the bound tracking fact"):
            quality.certify(self.project, staged["pending_id"], self.write_json("event-fingerprint-mutation.json", packet))

        packet = review_packet(1, staged["revision"], {"reader-1": None, "reader-2": None}, kind="revision", parent=parent, base=base, outline_sha256=staged["outline_sha256"])
        packet["posthoc_extraction"]["authoritative_events"].pop()
        with self.assertRaisesRegex(quality.QualityError, "cover every same-chapter tracking fact exactly once"):
            quality.certify(self.project, staged["pending_id"], self.write_json("event-subset-mutation.json", packet))

        packet = review_packet(1, staged["revision"], {"reader-1": None, "reader-2": None}, kind="revision", parent=parent, base=base, outline_sha256=staged["outline_sha256"])
        packet["final_validation"]["execution"]["candidate_revision"] = parent
        with self.assertRaisesRegex(quality.QualityError, "not bound to the candidate revision"):
            quality.certify(self.project, staged["pending_id"], self.write_json("validator-binding-mutation.json", packet))

    def test_revision_target_and_quality_regressions_cannot_advance(self) -> None:
        self.stage_certify_accept(1, 1)
        candidate, txn = self.write_chapter_inputs(1, 5, mode="revision")
        base = quality.manifest_for(self.project)
        parent = base["chapters"]["1"]["revision"]
        staged = quality.stage(
            self.project,
            1,
            candidate,
            txn,
            kind="revision",
            resolution="within_user_band",
            metadata={"finding_ids": ["LOGIC-TARGET"], "impact_regions": ["决定的直接后果"], "repair_scope": "local"},
        )

        missing = review_packet(
            1,
            staged["revision"],
            {"reader-1": None, "reader-2": None},
            kind="revision",
            parent=parent,
            base=base,
            outline_sha256=staged["outline_sha256"],
            finding_ids=["UNRELATED"],
        )
        with self.assertRaisesRegex(quality.QualityError, "account for every staged target finding"):
            quality.certify(self.project, staged["pending_id"], self.write_json("missing-target.json", missing))

        relabeled = review_packet(
            1,
            staged["revision"],
            {"reader-1": None, "reader-2": None},
            kind="revision",
            parent=parent,
            base=base,
            outline_sha256=staged["outline_sha256"],
            finding_ids=["LOGIC-TARGET"],
        )
        relabeled["perspectives"]["story-logic"]["findings"][0].update({
            "disposition": "FALSE_POSITIVE",
            "rationale": "试图把失败修法倒推成误报。",
        })
        with self.assertRaisesRegex(quality.QualityError, "independently FIXED_VERIFIED"):
            quality.certify(self.project, staged["pending_id"], self.write_json("relabeled-target.json", relabeled))

        worse = review_packet(
            1,
            staged["revision"],
            {"reader-1": None, "reader-2": None},
            kind="revision",
            parent=parent,
            base=base,
            outline_sha256=staged["outline_sha256"],
            finding_ids=["LOGIC-TARGET"],
        )
        worse["selection_protocol"]["improvement_dimensions"]["voice"] = "worse"
        certified = quality.certify(self.project, staged["pending_id"], self.write_json("worse-dimension.json", worse))
        self.assertFalse(certified["eligible"])
        self.assertEqual(certified["selection_status"], "FIX_FAILED")
        with self.assertRaisesRegex(quality.QualityError, "cannot be accepted"):
            quality.accept(self.project, staged["pending_id"])

    def test_rollback_creates_a_new_generation_without_overwriting_history(self) -> None:
        first = self.stage_certify_accept(1, 1)
        original_revision = first["revision"]
        revised = self.stage_certify_accept(1, 3, kind="revision", mode="revision")
        self.assertNotEqual(revised["revision"], original_revision)
        current = quality.manifest_for(self.project)
        current_revision = current["chapters"]["1"]["revision"]
        state = tracking.load_state(self.project)
        rollback_txn = self.write_json(
            "rollback-transaction.json",
            transaction(1, state["state_revision"], mode="revision"),
        )
        staged = self.run_cli(
            "rollback",
            "--project", self.project,
            "--chapter", 1,
            "--revision", original_revision,
            "--tracking-input", rollback_txn,
            "--reason", "新修法损害人物声线，恢复已知旧版。",
        )
        packet = review_packet(
            1,
            original_revision,
            {"reader-1": None, "reader-2": None},
            kind="revision",
            parent=current_revision,
            base=current,
            outline_sha256=staged["outline_sha256"],
            finding_ids=[],
        )
        packet["perspectives"]["story-logic"]["findings"] = []
        certified = quality.certify(
            self.project,
            staged["pending_id"],
            self.write_json("rollback-review.json", packet),
        )
        self.assertTrue(certified["eligible"])
        accepted = quality.accept(self.project, staged["pending_id"])
        self.assertEqual(accepted["revision"], original_revision)
        self.assertNotEqual(accepted["generation_id"], revised["generation_id"])
        current_body, _ = quality.revision_paths(quality.quality_root(self.project), 1, current_revision)
        self.assertTrue(current_body.is_file(), "rollback must preserve the superseded immutable revision")
        self.assertEqual(quality.check(self.project)["status"], "pass")

    def test_outline_revision_cli_requires_authorized_real_change(self) -> None:
        old_plan = self.root / "old-plan.md"
        new_plan = self.root / "new-plan.md"
        old_plan.write_text("# 第一卷\n旧目标。\n", encoding="utf-8")
        new_plan.write_text("# 第一卷\n新目标与新代价。\n", encoding="utf-8")
        decision = self.write_json("outline-decision.json", {
            "diagnosis": "multi_chapter_structure",
            "earliest_divergent_chapter": 3,
            "author_approval": "作者批准从第 3 章起调整卷纲与细纲。",
            "retrospective_relabel": False,
        })
        recorded = self.run_cli(
            "record-outline-revision",
            "--project", self.project,
            "--old", old_plan,
            "--new", new_plan,
            "--input", decision,
        )
        self.assertEqual(recorded["status"], "recorded")
        self.assertEqual(recorded["rebuild_from_chapter"], 3)
        stored = self.project / ".story-quality/outline-revisions/plans"
        self.assertEqual(
            {path.stem for path in stored.glob("*.md")},
            {quality.sha_file(old_plan), quality.sha_file(new_plan)},
        )
        unchanged = self.run_cli(
            "record-outline-revision",
            "--project", self.project,
            "--old", old_plan,
            "--new", old_plan,
            "--input", decision,
            expect=2,
        )
        self.assertEqual(unchanged["status"], "error")
        self.assertIn("real plan change", unchanged["message"])

    def test_structural_revision_and_dialogue_samples_cannot_self_exempt(self) -> None:
        self.stage_certify_accept(1, 1)
        candidate, txn = self.write_chapter_inputs(1, 4, mode="revision")
        base = quality.manifest_for(self.project)
        parent = base["chapters"]["1"]["revision"]
        staged = quality.stage(
            self.project,
            1,
            candidate,
            txn,
            kind="revision",
            resolution="within_user_band",
            metadata={
                "finding_ids": ["STRUCTURE-1"],
                "impact_regions": ["全章因果顺序"],
                "repair_scope": "structural",
                "author_authorization": "作者批准结构性重写。",
            },
        )
        packet = review_packet(
            1,
            staged["revision"],
            {"reader-1": None, "reader-2": None},
            kind="revision",
            parent=parent,
            base=base,
            outline_sha256=staged["outline_sha256"],
            finding_ids=["STRUCTURE-1"],
        )
        packet["selection_protocol"]["variants"] = {"premarked_key_chapter": False}
        with self.assertRaisesRegex(quality.QualityError, "require.*both version artifact sets"):
            quality.certify(self.project, staged["pending_id"], self.write_json("structural-self-exempt.json", packet))

        other = self.root / "dialogue-book"
        other.mkdir()
        (other / "大纲").mkdir()
        (other / "正文").mkdir()
        (other / "草稿/待验收").mkdir(parents=True)
        tracking.initialize(other, initial())
        quality.initialize(other)
        (other / "大纲/细纲_第001章.md").write_text(
            "- 字数目标：1000 字\n- 字数口径：visible_chars_v1\n"
            "- 结尾拍ID/类型：EB-01-001；choice；作出决定\n"
            "- 期待ID/类型：EX-01-001；aftermath；决定的后果\n"
            "| # | 情节点（谁做了什么） | 功能标签 | 执行边界 |\n|---|---|---|---|\n"
            "| 1 | 甲作出决定 | 推进 | 不新增支线 |\n",
            encoding="utf-8",
        )
        dialogue_line = "「先把门关上。」甲说。"
        dialogue_body = other / "草稿/待验收/第001章_台词测试.md"
        dialogue_body.write_text(f"# 第001章 台词测试\n{dialogue_line}\n" + "字" * 1000, encoding="utf-8")
        txn_path = self.write_json("dialogue-txn.json", transaction(1, 0))
        dialogue_staged = quality.stage(
            other, 1, dialogue_body, txn_path, kind="draft", resolution="within_user_band", metadata={}
        )
        dialogue_base = quality.manifest_for(other)
        dialogue_packet = review_packet(
            1,
            dialogue_staged["revision"],
            {"reader-1": None, "reader-2": None},
            base=dialogue_base,
            outline_sha256=dialogue_staged["outline_sha256"],
        )
        title_spoof = "# 第001章 台词测试"
        title_sample = {
            "line_text": title_spoof,
            "line_sha256": quality.sha_bytes(title_spoof.encode()),
            "expected_speaker": "甲",
            "predicted_speaker": "甲",
            "swapped_predicted_speaker": "乙",
            "speaker_swap_changed": True,
        }
        dialogue_packet["selection_protocol"]["dialogue_test"] = {
            "applicable": True,
            "scope": "voice-bearing-only",
            "blinded": True,
            "voice_card_provided": True,
            "prior_context_provided": True,
            "global_accuracy_threshold": False,
            "speaker_swap_diagnostic": True,
            "catchphrase_fix": False,
            "voice_bearing_line_count": 1,
            "samples": [title_sample],
            "run_id": "dialogue-title-spoof-run",
            "input_fingerprint": quality.sha_json([title_sample]),
        }
        with self.assertRaisesRegex(quality.QualityError, "detected voice-bearing line"):
            quality.certify(other, dialogue_staged["pending_id"], self.write_json("dialogue-title-spoof.json", dialogue_packet))

    def test_pending_evidence_and_init_paths_are_immutable(self) -> None:
        candidate, txn = self.write_chapter_inputs(1, 1)
        base = quality.manifest_for(self.project)
        staged = quality.stage(
            self.project, 1, candidate, txn, kind="draft", resolution="within_user_band", metadata={}
        )
        packet = review_packet(
            1,
            staged["revision"],
            {"reader-1": None, "reader-2": None},
            base=base,
            outline_sha256=staged["outline_sha256"],
        )
        quality.certify(self.project, staged["pending_id"], self.write_json("valid-before-tamper.json", packet))
        certificate_path = quality.quality_root(self.project) / "pending" / staged["pending_id"] / "certificate.json"
        certificate = json.loads(certificate_path.read_text(encoding="utf-8"))
        certificate["packet"]["posthoc_extraction"]["authoritative_events"][0]["data"]["after"] = "伪造关系"
        certificate_path.write_text(json.dumps(certificate, ensure_ascii=False), encoding="utf-8")
        with self.assertRaisesRegex(quality.QualityError, "packet hash mismatch"):
            quality.accept(self.project, staged["pending_id"])

        second_candidate, second_txn = self.write_chapter_inputs(1, 2)
        second = quality.stage(
            self.project, 1, second_candidate, second_txn, kind="draft", resolution="within_user_band", metadata={}
        )
        pending_txn = quality.quality_root(self.project) / "pending" / second["pending_id"] / "tracking-transaction.json"
        pending_txn.write_text(pending_txn.read_text(encoding="utf-8") + " ", encoding="utf-8")
        second_packet = review_packet(
            1,
            second["revision"],
            {"reader-1": None, "reader-2": None},
            base=base,
            outline_sha256=second["outline_sha256"],
        )
        with self.assertRaisesRegex(quality.QualityError, "tracking transaction changed after staging"):
            quality.certify(self.project, second["pending_id"], self.write_json("transaction-toctou.json", second_packet))

        third_candidate, third_txn = self.write_chapter_inputs(1, 3)
        third = quality.stage(
            self.project, 1, third_candidate, third_txn, kind="draft", resolution="within_user_band", metadata={}
        )
        live_state = self.project / "追踪/_tracking-state.json"
        original_state = live_state.read_text(encoding="utf-8")
        live_state.write_text(original_state + " ", encoding="utf-8")
        third_packet = review_packet(
            1,
            third["revision"],
            {"reader-1": None, "reader-2": None},
            base=base,
            outline_sha256=third["outline_sha256"],
        )
        with self.assertRaisesRegex(quality.QualityError, "tracking projection differs from HEAD"):
            quality.certify(self.project, third["pending_id"], self.write_json("live-state-toctou.json", third_packet))
        live_state.write_text(original_state, encoding="utf-8")

        unsafe = self.root / "unsafe-init"
        unsafe.mkdir()
        (unsafe / "正文").mkdir()
        tracking.initialize(unsafe, initial())
        outside = self.root / "outside-quality-root"
        outside.mkdir()
        (unsafe / ".story-quality").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(quality.QualityError, "symbolic-link"):
            quality.initialize(unsafe)
        self.assertEqual(list(outside.iterdir()), [])

    def test_longitudinal_contract_requires_human_cumulative_blind_read(self) -> None:
        arms = []
        for label in ("A", "B"):
            artifacts = []
            for chapter in range(1, 16):
                body = f"# 第{chapter}章\n{label} arm body {chapter}"
                artifacts.append({"chapter": chapter, "body": body, "revision": quality.sha_bytes(body.encode())})
            arms.append({"label": label, "chapter_artifacts": artifacts})
        for arm in arms:
            arm["arm_sha256"] = quality.sha_json([
                {"chapter": row["chapter"], "revision": row["revision"]} for row in arm["chapter_artifacts"]
            ])
        def observations() -> list[dict[str, object]]:
            return [
                {
                    "chapter": chapter, "first_friction": "无明显摩擦", "strongest_read_on": "人物选择",
                    "end_expectation": "选择的后果", "cumulative_fatigue": "无明显累积疲劳",
                    "target_emotion_received": True, "continued": True,
                }
                for chapter in range(1, 16)
            ]
        readers = [
            {
                "reader_id": "H1", "blind_code": "X7", "arm_order": ["A", "B"],
                "order_randomized": True, "randomization_nonce": "reader-H1-order",
                "read_from_chapter": 1, "read_through_chapter": 15,
                "arm_observations": {"A": observations(), "B": observations()},
                "final_preference": "A", "final_reason": "因果更清楚。",
            },
            {
                "reader_id": "H2", "blind_code": "Q2", "arm_order": ["B", "A"],
                "order_randomized": True, "randomization_nonce": "reader-H2-order",
                "read_from_chapter": 1, "read_through_chapter": 15,
                "arm_observations": {"A": observations(), "B": observations()},
                "final_preference": "A", "final_reason": "累计阅读更顺。",
            },
        ]
        allocation = [
            {key: row[key] for key in ("reader_id", "blind_code", "arm_order", "randomization_nonce")}
            for row in readers
        ]
        mapping = {"revealed_after_observations": True, "baseline_label": "B", "candidate_label": "A"}
        arm_hashes = {arm["label"]: arm["arm_sha256"] for arm in arms}
        experiment = {
            "schema": quality.EXPERIMENT_SCHEMA,
            "chapters": 15,
            "blind": True,
            "order_randomized": True,
            "arms": arms,
            "human_cumulative_readers": readers,
            "allocation_sha256": quality.sha_json(allocation),
            "sample_size_plan": {
                "method": "exact_minimum_with_underpowered_warning", "planned": 2, "completed": 2,
                "rationale": "先做完整覆盖的两人试验，正式结论前按试验方差扩样。", "underpowered_warning": True,
            },
            "llm_retention_role": "proxy_only",
            "cost_limited": False,
            "blind_mapping": mapping,
            "outcome": {
                "winner": "candidate",
                "judge_run_id": "human-experiment-judge",
                "rationale": "两名累计读者都偏好盲标 A；揭盲后 A 为候选方案。",
                "input_fingerprint": quality.sha_json({
                    "arm_hashes": arm_hashes,
                    "reader_result_sha256s": [quality.sha_json({
                        "reader_id": row["reader_id"],
                        "blind_code": row["blind_code"],
                        "arm_order": row["arm_order"],
                        "randomization_nonce": row["randomization_nonce"],
                        "arm_observations": row["arm_observations"],
                        "final_preference": row["final_preference"],
                        "final_reason": row["final_reason"],
                    }) for row in readers],
                    "blind_mapping": mapping,
                    "decision_rule": "strict-human-preference-majority-v1",
                }),
            },
        }
        experiment_path = self.write_json("experiment.json", experiment)
        result = self.run_cli("check-experiment", "--input", experiment_path)
        self.assertEqual(
            (result["status"], result["winner"], result["product_release_pass"], result["release_gate_status"]),
            ("historical_shadow_only", "candidate", False, "BLOCKED_LEGACY_SCHEMA"),
        )

        overlapping = copy.deepcopy(experiment)
        overlapping["arms"][1]["chapter_artifacts"][0] = copy.deepcopy(overlapping["arms"][0]["chapter_artifacts"][0])
        overlapping["arms"][1]["arm_sha256"] = quality.sha_json([
            {"chapter": row["chapter"], "revision": row["revision"]}
            for row in overlapping["arms"][1]["chapter_artifacts"]
        ])
        with self.assertRaisesRegex(quality.QualityError, "distinct artifacts"):
            quality.validate_experiment(self.write_json("experiment-overlap.json", overlapping))

        fake_body = copy.deepcopy(experiment)
        fake_body["arms"][0]["chapter_artifacts"][0]["body"] += " tampered"
        with self.assertRaisesRegex(quality.QualityError, "not bound to its text artifact"):
            quality.validate_experiment(self.write_json("experiment-body-mutation.json", fake_body))

        fake_mapping = copy.deepcopy(experiment)
        fake_mapping["blind_mapping"]["candidate_label"] = fake_mapping["blind_mapping"]["baseline_label"]
        with self.assertRaisesRegex(quality.QualityError, "distinct blind arms"):
            quality.validate_experiment(self.write_json("experiment-mapping-mutation.json", fake_mapping))

        fake_human = copy.deepcopy(experiment)
        fake_human["human_cumulative_readers"][0]["reader_id"] = fake_human["human_cumulative_readers"][1]["reader_id"]
        with self.assertRaisesRegex(quality.QualityError, "unique"):
            quality.validate_experiment(self.write_json("experiment-fake-human.json", fake_human))

        one_arm = copy.deepcopy(experiment)
        one_arm["human_cumulative_readers"][0]["arm_observations"].pop("B")
        with self.assertRaisesRegex(quality.QualityError, "observations for both blind arms"):
            quality.validate_experiment(self.write_json("experiment-one-arm.json", one_arm))

        false_winner = copy.deepcopy(experiment)
        for row in false_winner["human_cumulative_readers"]:
            row["final_preference"] = mapping["baseline_label"]
            row["final_reason"] = "累计阅读后基线更清楚。"
        false_winner["outcome"]["input_fingerprint"] = quality.sha_json({
            "arm_hashes": arm_hashes,
            "reader_result_sha256s": [quality.sha_json({
                "reader_id": row["reader_id"],
                "blind_code": row["blind_code"],
                "arm_order": row["arm_order"],
                "randomization_nonce": row["randomization_nonce"],
                "arm_observations": row["arm_observations"],
                "final_preference": row["final_preference"],
                "final_reason": row["final_reason"],
            }) for row in false_winner["human_cumulative_readers"]],
            "blind_mapping": mapping,
            "decision_rule": "strict-human-preference-majority-v1",
        })
        with self.assertRaisesRegex(quality.QualityError, "not derived from the human reader preferences"):
            quality.validate_experiment(self.write_json("experiment-false-winner.json", false_winner))

    def test_p1_strength_shadow_enforce_and_l2_reopen_end_to_end(self) -> None:
        candidate1, txn1 = self.write_p1_chapter_inputs(1, 21)
        staged1 = quality.stage(self.project, 1, candidate1, txn1, kind="draft", resolution="within_user_band", metadata={})
        packet1 = self.p1_packet(staged1, delivered=True)
        cert1 = quality.certify(self.project, staged1["pending_id"], self.write_json("p1-shadow.json", packet1))
        self.assertEqual((cert1["strength_mode"], cert1["strength_status"]), ("SHADOW", "PASS"))
        quality.accept(self.project, staged1["pending_id"])

        calibration = self.install_heldout_calibration("heldout-v1")
        quality.configure_policy(self.project, self.write_json("enforce-policy.json", enforce_policy(calibration, activated_from_chapter=2)))

        candidate2, txn2 = self.write_p1_chapter_inputs(2, 22)
        staged2 = quality.stage(self.project, 2, candidate2, txn2, kind="draft", resolution="within_user_band", metadata={})
        flat_packet = self.p1_packet(staged2, delivered=False)
        flat_cert = quality.certify(self.project, staged2["pending_id"], self.write_json("p1-flat.json", flat_packet))
        self.assertEqual(flat_cert["selection_status"], "REOPEN_REQUIRED")
        self.assertFalse(flat_cert["eligible"])
        with self.assertRaisesRegex(quality.QualityError, "candidate cannot be accepted"):
            quality.accept(self.project, staged2["pending_id"])

        certificate_path = self.project / ".story-quality/pending" / staged2["pending_id"] / "certificate.json"
        certificate = json.loads(certificate_path.read_text(encoding="utf-8"))
        reopen_request = {
            "schema": quality.REOPEN_SCHEMA,
            "pending_id": staged2["pending_id"],
            "level": "L2",
            "simulation_only": False,
            "localized_regions": [],
            "author_authorization": "作者批准在当前细纲内调整场景取舍和信息顺序。",
            "search_scope": {"allowed": ["opening", "scene-selection", "information-order"], "forbidden": ["plot-points", "POV"]},
            "reason_codes": certificate["packet"]["strength_gate"]["reason_codes"],
        }
        opened = quality.open_reopen_case(self.project, self.write_json("reopen-l2.json", reopen_request))
        arm_paths = []
        for index, arm_id in enumerate(("arm-a", "arm-b"), start=31):
            directory = self.root / arm_id
            directory.mkdir()
            body = directory / "第002章_代际测试.md"
            body.write_text(body_text(2, index), encoding="utf-8")
            case = quality.load_reopen_case(self.project, opened["case_id"])
            metadata = self.reopen_arm_metadata(case, arm_id, body, delivered=arm_id == "arm-b")
            quality.record_reopen_arm(self.project, opened["case_id"], self.write_json(f"{arm_id}.json", metadata), body, None)
            arm_paths.append((arm_id, body))
        self.resolve_reopen(
            opened["case_id"], arm_order=["arm-b", "arm-a"], outcome="selected",
            winner_arm_id="arm-b", synthetic=False, prefix="l2",
        )
        winner_path = dict(arm_paths)["arm-b"]
        selected_case = quality.load_reopen_case(self.project, opened["case_id"])
        staged_reopen = quality.stage(
            self.project, 2, winner_path, txn2, kind="draft", resolution="within_user_band",
            metadata={
                "revision_intent": "strength_reopen", "reopen_case_id": opened["case_id"],
                "reopen_arm_id": "arm-b", "strength_certificate_sha256": selected_case["strength_certificate_sha256"],
                "simulation_only": False,
                "impact_regions": ["全章场景取舍与信息顺序"], "repair_scope": "structural",
            },
        )
        pass_packet = self.p1_packet(staged_reopen, delivered=True)
        certified = quality.certify(self.project, staged_reopen["pending_id"], self.write_json("reopen-selected-review.json", pass_packet))
        self.assertEqual((certified["selection_status"], certified["strength_status"]), ("ACCEPT_CANDIDATE", "PASS"))
        accepted = quality.accept(self.project, staged_reopen["pending_id"])
        self.assertEqual(accepted["chapter"], 2)

    def test_p1_shadow_reopen_is_executable_but_cannot_advance_head(self) -> None:
        candidate, txn = self.write_p1_chapter_inputs(1, 24)
        staged = quality.stage(self.project, 1, candidate, txn, kind="draft", resolution="within_user_band", metadata={})
        flat_packet = self.p1_packet(staged, delivered=False)
        result = quality.certify(self.project, staged["pending_id"], self.write_json("shadow-flat.json", flat_packet))
        self.assertEqual((result["strength_mode"], result["strength_status"]), ("SHADOW", "FLAT"))
        self.assertEqual(result["selection_status"], "ACCEPT_CANDIDATE")
        certificate = json.loads(
            (self.project / ".story-quality/pending" / staged["pending_id"] / "certificate.json").read_text(encoding="utf-8")
        )
        request = {
            "schema": quality.REOPEN_SCHEMA,
            "pending_id": staged["pending_id"],
            "level": "L2",
            "simulation_only": True,
            "localized_regions": [],
            "author_authorization": "作者批准只做 SHADOW 流程演练。",
            "search_scope": {"allowed": ["opening", "scene-selection", "information-order"]},
            "reason_codes": certificate["packet"]["strength_gate"]["reason_codes"],
        }
        opened = quality.open_reopen_case(self.project, self.write_json("shadow-reopen.json", request))
        arm_paths: dict[str, Path] = {}
        for index, arm_id in enumerate(("shadow-a", "shadow-b"), start=35):
            directory = self.root / arm_id
            directory.mkdir()
            body = directory / "第001章_代际测试.md"
            body.write_text(body_text(1, index), encoding="utf-8")
            case = quality.load_reopen_case(self.project, opened["case_id"])
            metadata = self.reopen_arm_metadata(case, arm_id, body, delivered=arm_id == "shadow-b")
            quality.record_reopen_arm(
                self.project, opened["case_id"], self.write_json(f"{arm_id}-meta.json", metadata), body, None,
            )
            arm_paths[arm_id] = body
        unrelated_readers = []
        for index in (1, 2):
            raw = {"weather": "sunny", "reader_index": index}
            unrelated_readers.append({
                "reader_id": f"unrelated-{index}", "blind_code": f"unrelated-blind-{index}",
                "evidence_type": "human", "raw_observations": raw,
                "raw_observation_sha256": quality.sha_json(raw),
                "persona_id": "core-reader", "persona_profile": CORE_PROFILE,
                "persona_profile_sha256": quality.sha_json(CORE_PROFILE),
            })
        unrelated_sha256 = self.record_evidence(
            "unrelated-shadow-selector", kind="human_reader_import", source_kind="synthetic_fixture",
            artifact={"story_package_ids": [opened["case_id"]], "reader_count": 2, "readers": unrelated_readers},
        )
        with self.assertRaisesRegex(quality.QualityError, "blindly bound"):
            self.resolve_reopen(
                opened["case_id"], arm_order=["shadow-b", "shadow-a"], outcome="selected",
                winner_arm_id="shadow-b", synthetic=True, prefix="shadow-invalid",
                evidence_sha256=unrelated_sha256,
            )
        stored_case = quality.load_reopen_case(self.project, opened["case_id"])
        stored_arm = stored_case["arms"][0]
        reader_artifact = self.project / ".story-quality/reopen-cases" / opened["case_id"] / stored_arm["reader_evidence_artifacts"][0]["path"]
        reader_artifact_text = reader_artifact.read_text(encoding="utf-8")
        reader_artifact.unlink()
        with self.assertRaisesRegex(quality.QualityError, "unable to read reopen immutable reader evidence"):
            quality.revalidate_reopen_arm(self.project, stored_case, stored_arm)
        reader_artifact.write_text(reader_artifact_text, encoding="utf-8")
        self.resolve_reopen(
            opened["case_id"], arm_order=["shadow-b", "shadow-a"], outcome="selected",
            winner_arm_id="shadow-b", synthetic=True, prefix="shadow-l2",
        )
        selected_case = quality.load_reopen_case(self.project, opened["case_id"])
        simulated = quality.stage(
            self.project, 1, arm_paths["shadow-b"], txn, kind="draft", resolution="within_user_band",
            metadata={
                "revision_intent": "strength_reopen",
                "reopen_case_id": opened["case_id"],
                "reopen_arm_id": "shadow-b",
                "strength_certificate_sha256": selected_case["strength_certificate_sha256"],
                "simulation_only": True,
                "impact_regions": ["全章场景取舍与信息顺序"],
                "repair_scope": "structural",
            },
        )
        pass_packet = self.p1_packet(simulated, delivered=True)
        quality.certify(self.project, simulated["pending_id"], self.write_json("shadow-selected-review.json", pass_packet))
        with self.assertRaisesRegex(quality.QualityError, "simulation candidates"):
            quality.accept(self.project, simulated["pending_id"])
        self.assertEqual(quality.manifest_for(self.project)["chapters"], {})

    def test_p1_enforce_requires_two_independent_persona_readers(self) -> None:
        calibration = self.install_heldout_calibration("heldout-evidence")
        quality.configure_policy(self.project, self.write_json("evidence-policy.json", enforce_policy(calibration, activated_from_chapter=1)))
        candidate, txn = self.write_p1_chapter_inputs(1, 33)
        staged = quality.stage(self.project, 1, candidate, txn, kind="draft", resolution="within_user_band", metadata={})
        packet = self.p1_packet(staged, delivered=True)
        cohort = packet["reader_evidence"]["cohort"]
        alternate_profile = {"genre_familiarity": "low", "reading_history": "fresh"}
        cohort[1]["persona_id"] = "core-reader"
        cohort[1]["persona_profile"] = alternate_profile
        cohort[1]["persona_profile_sha256"] = quality.sha_json(alternate_profile)
        state_hashes = []
        for row in cohort:
            normalized = copy.deepcopy(row)
            normalized["chapter"] = 1
            normalized.pop("state_hash", None)
            state_hashes.append(quality.sha_json(normalized))
        packet["reader_evidence"]["judge"]["input_fingerprint"] = quality.sha_json({
            "outline_sha256": staged["outline_sha256"],
            "reader_state_hashes": state_hashes,
        })
        packet["strength_gate"] = {
            **quality.derive_strength_gate(staged, staged["quality_policy"], cohort),
            "derived": True,
        }
        certificate = quality.certify(
            self.project, staged["pending_id"], self.write_json("insufficient-reader-review.json", packet)
        )
        self.assertEqual((certificate["strength_status"], certificate["selection_status"]), (
            "INSUFFICIENT_EVIDENCE", "EVIDENCE_REQUIRED",
        ))
        self.assertFalse(certificate["eligible"])

    def test_p1_active_policy_rejects_calibration_tampering(self) -> None:
        calibration = self.install_heldout_calibration("heldout-tamper")
        development = quality.calibration_by_hash(self.project, calibration["development_calibration_sha256"])
        development_human = quality.evidence_by_hash(
            self.project, development["evidence"]["human_reader_import_sha256"],
        )
        heldout_human = quality.evidence_by_hash(
            self.project, calibration["evidence"]["human_reader_import_sha256"],
        )
        reused_artifact = copy.deepcopy(heldout_human["artifact"])
        reused_artifact["readers"][0]["reader_id"] = development_human["artifact"]["readers"][0]["reader_id"]
        reused_human_hash = self.record_evidence(
            "heldout-tamper-reused-development-reader", kind="human_reader_import",
            source_kind="human_blind_import", artifact=reused_artifact,
        )
        reused_calibration = copy.deepcopy(calibration)
        reused_calibration["calibration_id"] = "heldout-tamper-reader-reuse-invalid"
        reused_calibration["evidence"]["human_reader_import_sha256"] = reused_human_hash
        evidence_input = {
            "story_package_sha256s": reused_calibration["evidence"]["story_package_sha256s"],
            "human_reader_import_sha256": reused_human_hash,
            "misfire_control_sha256s": reused_calibration["evidence"]["misfire_control_sha256s"],
            "reopen_validation_sha256": reused_calibration["evidence"]["reopen_validation_sha256"],
        }
        reused_calibration["evidence"]["input_fingerprint"] = quality.sha_json(evidence_input)
        with self.assertRaisesRegex(quality.QualityError, "reuses development participant evidence: reader_id"):
            quality.validate_calibration_document(reused_calibration, self.project)
        quality.configure_policy(self.project, self.write_json("tamper-policy.json", enforce_policy(calibration, activated_from_chapter=1)))
        path = self.project / ".story-quality/calibration/heldout-tamper.json"
        tampered = json.loads(path.read_text(encoding="utf-8"))
        tampered["tampered_after_activation"] = True
        path.write_text(json.dumps(tampered, ensure_ascii=False), encoding="utf-8")
        with self.assertRaisesRegex(quality.QualityError, "calibration hash mismatch"):
            quality.active_policy(self.project)

    def test_p1_control_cannot_cite_nonexistent_reader_hashes(self) -> None:
        result = {"function_delivered": True, "false_positive_detected": False}
        artifact = {
            "control_kind": "low_pressure",
            "story_package_id": "story-a",
            "function_rule_name": "低压生活",
            "reader_evidence_bundle_sha256": quality.sha_bytes(b"nonexistent-human-bundle"),
            "reader_results": [
                {"reader_id": f"reader-{index}", "result": result, "result_sha256": quality.sha_json(result)}
                for index in (1, 2)
            ],
            "status": "PASS",
        }
        bundle = {
            "schema": quality.EVIDENCE_BUNDLE_SCHEMA,
            "evidence_id": "bad-control",
            "kind": "misfire_control",
            "source_kind": "human_blind_import",
            "synthetic": False,
            "collected_at": "2026-01-01T00:00:00Z",
            "producer_run_id": "bad-control-run",
            "artifact": artifact,
            "artifact_sha256": quality.sha_json(artifact),
        }
        with self.assertRaisesRegex(quality.QualityError, "unable to read recorded quality evidence"):
            quality.validate_evidence_bundle(bundle, self.project)

    def test_p1_strength_requires_a_shared_delivery_region(self) -> None:
        calibration = self.install_heldout_calibration("heldout-consensus")
        quality.configure_policy(self.project, self.write_json("consensus-policy.json", enforce_policy(calibration, activated_from_chapter=1)))
        candidate, txn = self.write_p1_chapter_inputs(1, 34)
        staged = quality.stage(self.project, 1, candidate, txn, kind="draft", resolution="within_user_band", metadata={})
        packet = self.p1_packet(staged, delivered=True)
        spoofed_cohort = copy.deepcopy(packet["reader_evidence"]["cohort"])
        spoofed_cohort[1]["measurements"]["strongest_read_on"]["scene_id"] = "scene-4"
        spoofed = quality.derive_strength_gate(staged, staged["quality_policy"], spoofed_cohort)
        self.assertEqual(spoofed["status"], "INSUFFICIENT_EVIDENCE")
        self.assertIn("reader-scene-reference-not-in-outline-catalog", spoofed["reason_codes"])
        packet["reader_evidence"]["cohort"][1]["measurements"]["strongest_read_on"]["scene_index"] = 4
        packet["reader_evidence"]["cohort"][1]["measurements"]["strongest_read_on"]["scene_id"] = "scene-4"
        state_hashes = []
        for row in packet["reader_evidence"]["cohort"]:
            normalized = copy.deepcopy(row)
            normalized["chapter"] = 1
            normalized.pop("state_hash", None)
            state_hashes.append(quality.sha_json(normalized))
        packet["reader_evidence"]["judge"]["input_fingerprint"] = quality.sha_json({
            "outline_sha256": staged["outline_sha256"], "reader_state_hashes": state_hashes,
        })
        packet["strength_gate"] = {
            **quality.derive_strength_gate(staged, staged["quality_policy"], packet["reader_evidence"]["cohort"]),
            "derived": True,
        }
        certificate = quality.certify(
            self.project, staged["pending_id"], self.write_json("split-delivery-review.json", packet)
        )
        self.assertEqual((certificate["strength_status"], certificate["selection_status"]), ("FLAT", "REOPEN_REQUIRED"))
        self.assertIn(
            "core-reader:planned-delivery-lacks-shared-region",
            packet["strength_gate"]["reason_codes"],
        )

    def test_p1_intentional_ambiguity_still_rejects_unplanned_hypotheses(self) -> None:
        calibration = self.install_heldout_calibration("heldout-ambiguity")
        quality.configure_policy(
            self.project,
            self.write_json("ambiguity-policy.json", enforce_policy(calibration, activated_from_chapter=1)),
        )
        candidate, txn = self.write_chapter_inputs(1, 36)
        outline = self.project / "大纲/细纲_第001章.md"
        contract = {
            "chapter_function": "有意多解",
            "target_emotion_id": "EMO-forward",
            "required_deliveries": ["hypothesis-space"],
            "allowed_expectation_ids": ["EX-01-001"],
            "allowed_hypothesis_ids": ["hypothesis-a"],
            "intentional_ambiguity": True,
            "scene_catalog": [{"scene_id": "scene-1", "scene_index": 1}],
        }
        outline.write_text(
            outline.read_text(encoding="utf-8")
            + "- P1质量契约："
            + json.dumps(contract, ensure_ascii=False, separators=(",", ":"))
            + "\n",
            encoding="utf-8",
        )
        staged = quality.stage(self.project, 1, candidate, txn, kind="draft", resolution="within_user_band", metadata={})
        packet = self.p1_packet(staged, delivered=True)
        cohort = packet["reader_evidence"]["cohort"]
        for row in cohort:
            row["measurements"]["strongest_read_on"]["function"] = "hypothesis-space"
        cohort[1]["measurements"]["end_expectation"]["hypothesis_ids"] = ["unplanned-hypothesis"]
        state_hashes = []
        for row in cohort:
            normalized = copy.deepcopy(row)
            normalized["chapter"] = 1
            normalized.pop("state_hash", None)
            state_hashes.append(quality.sha_json(normalized))
        packet["reader_evidence"]["judge"]["input_fingerprint"] = quality.sha_json({
            "outline_sha256": staged["outline_sha256"],
            "reader_state_hashes": state_hashes,
        })
        packet["strength_gate"] = {
            **quality.derive_strength_gate(staged, staged["quality_policy"], cohort),
            "derived": True,
        }
        result = quality.certify(
            self.project, staged["pending_id"], self.write_json("ambiguity-review.json", packet),
        )
        self.assertEqual((result["strength_status"], result["selection_status"]), ("FLAT", "REOPEN_REQUIRED"))
        self.assertIn(
            "core-reader:continuation-function-lacks-consensus",
            packet["strength_gate"]["reason_codes"],
        )

    def test_p1_l3_requires_authorization_and_selected_outline_activation(self) -> None:
        calibration = self.install_heldout_calibration("heldout-l3")
        quality.configure_policy(self.project, self.write_json("l3-policy.json", enforce_policy(calibration, activated_from_chapter=1)))
        candidate, txn = self.write_p1_chapter_inputs(1, 41)
        staged = quality.stage(self.project, 1, candidate, txn, kind="draft", resolution="within_user_band", metadata={})
        flat = self.p1_packet(staged, delivered=False)
        quality.certify(self.project, staged["pending_id"], self.write_json("l3-flat.json", flat))
        certificate_path = self.project / ".story-quality/pending" / staged["pending_id"] / "certificate.json"
        certificate = json.loads(certificate_path.read_text(encoding="utf-8"))

        direct_l3 = {
            "schema": quality.REOPEN_SCHEMA,
            "pending_id": staged["pending_id"],
            "level": "L3",
            "simulation_only": False,
            "localized_regions": [],
            "author_authorization": "作者批准本次 L3 结构分叉。",
            "search_scope": {"allowed": ["chapter-split", "event-order", "POV"]},
            "reason_codes": certificate["packet"]["strength_gate"]["reason_codes"],
        }
        with self.assertRaisesRegex(quality.QualityError, "L3 parent_reopen_case_id"):
            quality.open_reopen_case(self.project, self.write_json("direct-l3-bypass.json", direct_l3))

        l2_request = {
            "schema": quality.REOPEN_SCHEMA,
            "pending_id": staged["pending_id"],
            "level": "L2",
            "simulation_only": False,
            "localized_regions": [],
            "author_authorization": "作者批准先在原细纲内进行 L2 搜索。",
            "search_scope": {"allowed": ["opening", "scene-selection", "information-order"]},
            "reason_codes": certificate["packet"]["strength_gate"]["reason_codes"],
        }
        l2 = quality.open_reopen_case(self.project, self.write_json("l3-parent-l2.json", l2_request))
        for index, arm_id in enumerate(("l2-flat-a", "l2-flat-b"), start=45):
            directory = self.root / arm_id
            directory.mkdir()
            body = directory / "第001章_代际测试.md"
            body.write_text(body_text(1, index), encoding="utf-8")
            case = quality.load_reopen_case(self.project, l2["case_id"])
            metadata = self.reopen_arm_metadata(case, arm_id, body, delivered=False)
            quality.record_reopen_arm(self.project, l2["case_id"], self.write_json(f"{arm_id}-meta.json", metadata), body, None)
        self.resolve_reopen(
            l2["case_id"], arm_order=["l2-flat-b", "l2-flat-a"], outcome="all_flat",
            winner_arm_id=None, synthetic=False, prefix="l2-all-flat",
        )

        request = {
            "schema": quality.REOPEN_SCHEMA, "pending_id": staged["pending_id"], "level": "L3",
            "simulation_only": False, "parent_reopen_case_id": l2["case_id"],
            "localized_regions": [], "author_authorization": None,
            "search_scope": {"allowed": ["chapter-split", "event-order", "POV"]},
            "reason_codes": certificate["packet"]["strength_gate"]["reason_codes"],
        }
        with self.assertRaisesRegex(quality.QualityError, "author authorization"):
            quality.open_reopen_case(self.project, self.write_json("l3-no-auth.json", request))
        request["author_authorization"] = "作者批准本次 L3 结构分叉。"
        opened = quality.open_reopen_case(self.project, self.write_json("l3-auth.json", request))
        arms = []
        for index, arm_id in enumerate(("outline-a", "outline-b"), start=51):
            directory = self.root / arm_id
            directory.mkdir()
            body = directory / "第001章_代际测试.md"
            body.write_text(body_text(1, index), encoding="utf-8")
            outline = directory / f"{arm_id}.md"
            contract = p1_contract(1)
            outline.write_text(
                "- 字数目标：1000 字\n- 字数口径：visible_chars_v1\n"
                f"- 结构变体：{arm_id}\n"
                "- 结尾拍ID/类型：EB-01-001；choice；作出决定\n"
                "- 期待ID/类型：EX-01-001；aftermath；决定的后果\n"
                "- P1质量契约：" + json.dumps(contract, ensure_ascii=False, separators=(",", ":")) + "\n"
                "| # | 情节点（谁做了什么） | 功能标签 | 执行边界 |\n"
                "|---|---|---|---|\n"
                "| 1 | 甲看到当前证据 | 铺垫 | 不新增支线 |\n"
                "| 2 | 甲确认自己的目标 | 推进 | 不新增支线 |\n"
                "| 3 | 甲作出决定 | 选择 | 不新增支线 |\n"
                "| 4 | 决定产生可见后果 | 结果 | 不新增支线 |\n",
                encoding="utf-8",
            )
            case = quality.load_reopen_case(self.project, opened["case_id"])
            metadata = self.reopen_arm_metadata(
                case, arm_id, body, outline=outline, delivered=arm_id == "outline-b",
            )
            quality.record_reopen_arm(self.project, opened["case_id"], self.write_json(f"{arm_id}-meta.json", metadata), body, outline)
            arms.append((arm_id, body, outline))
        self.resolve_reopen(
            opened["case_id"], arm_order=["outline-a", "outline-b"], outcome="selected",
            winner_arm_id="outline-b", synthetic=False, prefix="l3",
        )
        winner = {row[0]: row for row in arms}["outline-b"]
        old_outline = self.project / "大纲/细纲_第001章.md"
        outline_decision = {
            "diagnosis": "chapter_design", "earliest_divergent_chapter": 1,
            "author_approval": request["author_authorization"], "retrospective_relabel": False,
            "reopen_case_id": opened["case_id"],
        }
        quality.record_outline_revision(self.project, old_outline, winner[2], self.write_json("l3-outline-decision.json", outline_decision))
        old_outline.write_text(winner[2].read_text(encoding="utf-8"), encoding="utf-8")
        selected_case = quality.load_reopen_case(self.project, opened["case_id"])
        staged_selected = quality.stage(
            self.project, 1, winner[1], txn, kind="draft", resolution="within_user_band",
            metadata={
                "revision_intent": "strength_reopen", "reopen_case_id": opened["case_id"],
                "reopen_arm_id": "outline-b", "strength_certificate_sha256": selected_case["strength_certificate_sha256"],
                "simulation_only": False,
                "impact_regions": ["章节切分、事件顺序与 POV"], "repair_scope": "structural",
            },
        )
        packet = self.p1_packet(staged_selected, delivered=True)
        quality.certify(self.project, staged_selected["pending_id"], self.write_json("l3-selected-review.json", packet))
        self.assertEqual(quality.accept(self.project, staged_selected["pending_id"])["chapter"], 1)

    def test_p1_checkpoint_outline_search_benchmark_and_golden_plan(self) -> None:
        for chapter in range(1, 4):
            self.stage_certify_accept(chapter, 60 + chapter)
        manifest = quality.manifest_for(self.project)
        reader_hashes = [chain["3"] for chain in manifest["reader_chains"].values() if "3" in chain]
        attachments = {
            "strength_summary": {"PASS": 2, "FLAT": 1, "INSUFFICIENT_EVIDENCE": 0},
            "character_core_tests": [{
                "character": "甲", "hypothetical_situation": "利益与承诺冲突时如何选择",
                "reader_choices": ["守约"], "rationale_chains": ["重承诺→承担损失→守约"],
                "bounded_surprise_allowed": True, "predictability_maximization": False,
            }],
            "memory_recall": [{"free_recall": ["共同决定"], "prompted_recall": ["会议室"], "recent_two_chapter_items": ["承担后果"], "exact_quote_required": False}],
            "emotion_curve": {"planned": [{"scene_index": 1, "intensity": 3}], "observed": [{"scene_index": 1, "intensity": 4}], "mechanical_match_required": False},
            "suspense_debt": [],
            "reader_cumulative_state": [],
        }
        checkpoint = {
            "schema": quality.CHECKPOINT_SCHEMA, "chapter": 3, "generation_id": manifest["generation_id"],
            "revision_sequence_sha256": quality.sha_json([manifest["chapters"][str(number)]["revision"] for number in range(1, 4)]),
            "reader_state_hashes": reader_hashes, "run_ids": ["checkpoint-character", "checkpoint-memory", "checkpoint-emotion"],
            "advisory_only": True, "correctness_impact": False, "attachments": attachments,
            "quality_alerts": [{"diagnosis": "chapter_design", "evidence": "一处强度信号需要观察", "action": "observe"}],
            "attention_required": True,
        }
        self.assertEqual(quality.record_checkpoint(self.project, self.write_json("checkpoint-3.json", checkpoint))["status"], "checkpoint_recorded")
        bad_checkpoint = copy.deepcopy(checkpoint)
        bad_checkpoint["chapter"] = 4
        with self.assertRaisesRegex(quality.QualityError, "checkpoint chapter"):
            quality.record_checkpoint(self.project, self.write_json("checkpoint-4.json", bad_checkpoint))

        variants = []
        for index in (1, 2):
            text = f"outline variant {index}"
            variants.append({
                "variant_id": f"variant-{index}", "outline_text": text,
                "outline_sha256": quality.sha_bytes(text.encode()),
                "sequence": [{"ending_beat_id": f"EB-{index}", "expectation_id": f"EX-{index}", "must_know": ["选择"], "must_not_know": ["答案"]}],
                "proxy_evaluation": {"run_id": f"proxy-{index}", "held_out_from_generation": True, "expectation_chain_breaks": 0, "same_type_streak": 1, "open_density_curve": [1], "emotion_curve": [3]},
            })
        search = {
            "schema": quality.OUTLINE_SEARCH_SCHEMA, "instrument_only": True,
            "proxy_only": True, "final_prose_validation_required": True,
            "variants": variants, "selected_variant_id": "variant-2", "selector_run_id": "outline-selector",
            "search_input_sha256": quality.sha_json([{"variant_id": row["variant_id"], "outline_sha256": row["outline_sha256"], "sequence": row["sequence"]} for row in variants]),
        }
        self.assertFalse(quality.record_outline_search(self.project, self.write_json("outline-search.json", search))["blocking"])

        dimension = {"candidate": 1.0, "reference": 1.2, "relative_difference": -0.1667, "confidence": 0.7}
        benchmark = {
            "schema": quality.STRUCTURAL_BENCHMARK_SCHEMA, "diagnostic_only": True, "blocking": False,
            "prohibited_comparisons": {"sentences": False, "plot_beats": False, "proper_nouns": False},
            "chapter": 3, "generation_id": manifest["generation_id"], "volume_position_ratio": 0.1,
            "dimensions": {key: copy.deepcopy(dimension) for key in ("event_density", "information_release", "ending_type_distribution", "emotion_intensity", "dialogue_narration_ratio")},
            "normalized_by_genre_and_position": True,
        }
        self.assertFalse(quality.record_structural_benchmark(self.project, self.write_json("benchmark.json", benchmark))["blocking"])

        self.install_heldout_calibration("golden-heldout")
        calibration = quality.read_json(
            quality.quality_root(self.project) / "calibration/golden-heldout-development.json",
            "development calibration fixture",
        )
        recorded = {"calibration_sha256": quality.sha_json(calibration)}
        arm_plans = [
            {
                "chapter": chapter,
                "outline_variants": 2,
                "prose_variants_per_outline": 1,
                "stop_rule": "one-per-outline",
                "selector_blinded": True,
                "held_out_final_readers": True,
            }
            for chapter in (1, 2, 3)
        ]
        prereg = {
            "allocation": "balanced",
            "stop_rule": "predeclared",
            "primary_endpoint": "held-out-human-preference",
            "arm_plans": arm_plans,
        }
        plan = {
            "schema": quality.GOLDEN_THREE_SCHEMA, "plan_only": True, "chapters": [1, 2, 3], "budget_preregistered": True,
            "fixed_six_arm_rule": False, "calibration_id": calibration["calibration_id"], "calibration_sha256": recorded["calibration_sha256"],
            "arm_plans": arm_plans,
            "preregistration": prereg, "preregistration_sha256": quality.sha_json(prereg),
        }
        golden_result = quality.record_golden_three_plan(self.project, self.write_json("golden-plan.json", plan))
        self.assertEqual((golden_result["status"], golden_result["plan_only"], golden_result["execution_ready"]), ("golden_three_plan_recorded", True, False))

    def test_p1_knowledge_source_order_is_a_correctness_gate(self) -> None:
        candidate, _ = self.write_chapter_inputs(1, 71)
        custom = transaction(1, 0)
        custom_event = custom["delta"]["timeline_events"][0]
        custom_event.update({
            "kind": "knowledge", "occurrence_order": 1,
            "knowledge": {"character": "甲", "fact_id": "FACT-door", "state": "knows", "source": "乙当面告知", "source_chapter": 1, "source_order": 1},
        })
        txn = self.write_json("knowledge-txn.json", custom)
        staged = quality.stage(self.project, 1, candidate, txn, kind="draft", resolution="within_user_band", metadata={})
        packet = review_packet(1, staged["revision"], {}, base=quality.manifest_for(self.project), outline_sha256=staged["outline_sha256"])
        packet["posthoc_extraction"]["authoritative_events"][0] = {
            "id": "KNOW-1", "kind": "knowledge", "confidence": "explicit", "occurrence_state": "occurred",
            "evidence": "乙先告知，甲随后行动", "tracking_event_id": "E001",
            "tracking_event_fingerprint": quality.tracking_event_fingerprint(custom_event),
            "data": {"character": "甲", "fact_id": "FACT-door", "state": "knows", "source": "乙当面告知", "source_chapter": 1, "source_order": 1, "occurrence_order": 1},
        }
        packet["posthoc_extraction"]["knowledge_prerequisites"] = [{
            "action_id": "ACTION-open-door", "character": "甲", "fact_id": "FACT-door",
            "action_occurrence_order": 2, "source_event_id": "KNOW-1",
        }]
        normalized_txn = tracking.normalize_transaction(self.project, tracking.load_state(self.project), custom)
        bindings = quality.tracking_event_bindings(normalized_txn["delta"]["timeline_events"], 1)
        bad = copy.deepcopy(packet)
        bad["posthoc_extraction"]["knowledge_prerequisites"][0]["action_occurrence_order"] = 1
        with self.assertRaisesRegex(quality.QualityError, "learned after the action"):
            quality.validate_review_packet(bad, staged, quality.manifest_for(self.project), tracking_events=bindings, candidate_body=candidate.read_text(encoding="utf-8"))
        quality.certify(self.project, staged["pending_id"], self.write_json("knowledge-review.json", packet))
        self.assertEqual(quality.accept(self.project, staged["pending_id"])["chapter"], 1)

    def test_p1_experiment_v2_preserves_negative_results_and_rejects_self_reported_formal_runs(self) -> None:
        def plan_experiment(seed: str, *, stage: str, reader_count: int) -> dict[str, object]:
            synthetic = stage == "pilot"
            source_kind = "synthetic_fixture" if synthetic else "held_out_original"
            story_package_id = f"package-{seed}"
            creative_package = {"genre": "legal", "premise": f"frozen-premise-{seed}"}
            story_package_artifact = {
                "story_package_id": story_package_id,
                "chapters": [
                    {
                        "chapter": chapter,
                        "body": f"source-{seed}-body-{chapter}",
                        "revision": quality.sha_bytes(f"source-{seed}-body-{chapter}".encode()),
                        "outline": f"source-{seed}-outline-{chapter}",
                        "outline_sha256": quality.sha_bytes(f"source-{seed}-outline-{chapter}".encode()),
                    }
                    for chapter in range(1, 16)
                ],
                "creative_package": creative_package,
                "creative_package_sha256": quality.sha_json(creative_package),
            }
            story_evidence_sha256 = self.record_evidence(
                f"experiment-package-{seed}", kind="story_package", source_kind=source_kind,
                artifact=story_package_artifact,
            )
            prereg = {
                "schema": quality.EXPERIMENT_PREREG_SCHEMA,
                "preregistration_id": f"story-prereg-{seed}",
                "scope": "story",
                "registered_at": "2026-01-01T00:00:00Z",
                "source_kind": source_kind,
                "synthetic": synthetic,
                "stage": stage,
                "story_package_id": story_package_id,
                "story_package_evidence_sha256": story_evidence_sha256,
                "sample_size_rule": {"planned": reader_count, "unit": "reader", "exact_completed_required": True},
                "expansion_rule": {"allowed": False, "rule": "none-after-registration"},
                "inclusion_rules": [{"rule_id": "completed-both-arms", "criterion": "reader completed both 15-chapter arms"}],
                "exclusion_rules": [{"rule_id": "identity-leak", "criterion": "reader learned treatment identity before final preference"}],
                "allocation_algorithm": "counterbalanced-paired-order",
                "random_seed_commitment": f"seed-{seed}",
                "order_balance_rule": "difference-at-most-one",
                "arm_treatments": ["P0", "P1"],
                "variant_budget": {"P0": 1, "P1": 3},
                "shared_max_visible_chars": 5000,
                "stop_rule": "freeze-before-reading",
                "primary_endpoint": "reader-final-preference",
                "primary_analysis": "strict-majority-plus-wilson-95",
                "sequence_contamination_plan": "report-arm-order-and-repeat-reading",
            }
            prereg_result = quality.record_experiment_preregistration(
                self.project, self.write_json(f"story-prereg-{seed}.json", prereg),
            )
            return {
                "synthetic": synthetic,
                "source_kind": source_kind,
                "story_package_id": story_package_id,
                "story_package_artifact": story_package_artifact,
                "story_evidence_sha256": story_evidence_sha256,
                "prereg": prereg,
                "prereg_sha256": prereg_result["preregistration_sha256"],
            }

        def make_experiment(
            seed: str,
            *,
            candidate_wins: bool,
            stage: str,
            reader_count: int,
            preference_pattern: list[str] | None = None,
            planned: dict[str, object] | None = None,
            workflow_max_visible_by_treatment: dict[str, int] | None = None,
        ) -> dict[str, object]:
            labels = ("A", "B")
            arms = []
            planned = planned or plan_experiment(seed, stage=stage, reader_count=reader_count)
            synthetic = bool(planned["synthetic"])
            source_kind = str(planned["source_kind"])
            story_package_id = str(planned["story_package_id"])
            story_package_artifact = planned["story_package_artifact"]
            story_evidence_sha256 = str(planned["story_evidence_sha256"])
            prereg = planned["prereg"]
            prereg_sha256 = str(planned["prereg_sha256"])
            common = {
                "creative_package_sha256": story_package_artifact["creative_package_sha256"],
                "author_identity_sha256": quality.sha_bytes(b"author"),
                "writer_identity_sha256": quality.sha_bytes(b"writer"),
                "model_identity_sha256": quality.sha_bytes(b"model"),
                "context_sha256": quality.sha_bytes(b"context"),
            }
            common_control_sha256 = quality.sha_bytes(f"common-control-{seed}".encode())
            outline_sha256s = [row["outline_sha256"] for row in story_package_artifact["chapters"]]
            for label, treatment in zip(labels, ("P1", "P0")):
                artifacts = []
                for chapter in range(1, 16):
                    body = f"# 第{chapter}章\n{seed}-{label}-{chapter}-" + "字" * 120
                    artifacts.append({"chapter": chapter, "body": body, "revision": quality.sha_bytes(body.encode())})
                provenance = {
                    **common,
                    "workflow_version": f"{treatment}-workflow-v1",
                    "arm_source_kind": "workflow_generated",
                    "story_package_id": story_package_id,
                    "story_package_evidence_sha256": story_evidence_sha256,
                    "variant_budget": prereg["variant_budget"],
                    "stop_rule": prereg["stop_rule"],
                    "common_control_sha256": common_control_sha256,
                }
                arm = {"label": label, "treatment": treatment, "provenance": provenance, "chapter_artifacts": artifacts}
                arm["arm_sha256"] = quality.sha_json([{"chapter": row["chapter"], "revision": row["revision"]} for row in artifacts])
                workflow_outputs = [{"chapter": row["chapter"], "revision": row["revision"]} for row in artifacts]
                workflow_evidence_sha256 = self.record_evidence(
                    f"workflow-{seed}-{treatment}",
                    kind="workflow_run",
                    source_kind="synthetic_fixture" if synthetic else "accepted_lifecycle",
                    artifact={
                        "story_package_id": story_package_id,
                        "treatment": treatment,
                        "workflow_version": provenance["workflow_version"],
                        "run_id": f"workflow-{seed}-{treatment}",
                        "started_at": "2026-01-01T00:00:00Z",
                        "completed_at": "2026-01-01T00:00:01Z",
                        "story_package_evidence_sha256": story_evidence_sha256,
                        "outputs": workflow_outputs,
                        "variant_budget": prereg["variant_budget"],
                        "shared_max_visible_chars": (
                            workflow_max_visible_by_treatment or {}
                        ).get(treatment, prereg["shared_max_visible_chars"]),
                        "common_control_sha256": common_control_sha256,
                        "common_provenance": common,
                        "treatment_budget_sha256": quality.sha_bytes(f"budget-{seed}-{treatment}".encode()),
                        "outline_sha256s": outline_sha256s,
                        "stop_rule": prereg["stop_rule"],
                        "output_fingerprint": quality.sha_json(workflow_outputs),
                    },
                )
                provenance["workflow_evidence_sha256"] = workflow_evidence_sha256
                arms.append(arm)
            workflow_receipts = [
                quality.evidence_record_by_hash(self.project, arm["provenance"]["workflow_evidence_sha256"])["recorded_by_lifecycle_at"]
                for arm in arms
            ]
            profile = {"genre_familiarity": "medium", "reading_history": "fresh"}
            readers = []
            for index in range(reader_count):
                order = ["A", "B"] if index % 2 == 0 else ["B", "A"]
                observations = {}
                for label in labels:
                    observations[label] = []
                    for chapter in range(1, 16):
                        measurements = reader_v2(
                            f"human-{index}", None, chapter=chapter,
                            revision=arms[0 if label == "A" else 1]["chapter_artifacts"][chapter - 1]["revision"],
                            input_fingerprint="unused", expectation_id=f"EX-01-{chapter:03d}",
                        )["measurements"]
                        observations[label].append({"chapter": chapter, "measurements": measurements})
                preferred = preference_pattern[index] if preference_pattern is not None else "A" if candidate_wins else "B"
                readers.append({
                    "reader_id": f"H-{seed}-{index}", "blind_code": f"C-{seed}-{index}",
                    "persona_id": "human-core", "persona_profile": profile,
                    "persona_profile_sha256": quality.sha_json(profile),
                    "arm_order": order, "randomization_nonce": f"nonce-{seed}-{index}",
                    "arm_observations": observations, "final_preference": preferred,
                    "final_reason": "累计阅读后这一臂更有继续阅读动力。",
                })
            imported_readers = []
            for row in readers:
                raw_observations = {
                    "arm_order": row["arm_order"],
                    "randomization_nonce": row["randomization_nonce"],
                    "arm_observations": row["arm_observations"],
                    "final_preference": row["final_preference"],
                    "final_reason": row["final_reason"],
                }
                imported_readers.append({
                    "reader_id": row["reader_id"],
                    "blind_code": row["blind_code"],
                    "evidence_type": "human",
                    "raw_observations": raw_observations,
                    "raw_observation_sha256": quality.sha_json(raw_observations),
                    "persona_id": row["persona_id"],
                    "persona_profile": row["persona_profile"],
                    "persona_profile_sha256": row["persona_profile_sha256"],
                })
            human_evidence_sha256 = self.record_evidence(
                f"experiment-humans-{seed}",
                kind="human_reader_import",
                source_kind="synthetic_fixture" if synthetic else "human_blind_import",
                artifact={
                    "story_package_ids": [story_package_id],
                    "reader_count": len(imported_readers),
                    "readers": imported_readers,
                },
            )
            human_receipt = quality.evidence_record_by_hash(self.project, human_evidence_sha256)["recorded_by_lifecycle_at"]
            for row in readers:
                row["human_evidence"] = {
                    "evidence_bundle_sha256": human_evidence_sha256,
                    "imported_reader_id": row["reader_id"],
                }
            allocation = [{key: row[key] for key in ("reader_id", "blind_code", "arm_order", "randomization_nonce", "persona_id", "persona_profile_sha256")} for row in readers]
            mapping = {"baseline_label": "B", "candidate_label": "A"}
            reader_results = [{
                "reader_id": row["reader_id"], "arm_order": row["arm_order"],
                "arm_observations": row["arm_observations"], "final_preference": row["final_preference"],
                "final_reason": row["final_reason"],
            } for row in readers]
            candidate_votes = sum(row["final_preference"] == "A" for row in readers)
            baseline_votes = sum(row["final_preference"] == "B" for row in readers)
            lower, upper = quality.wilson_interval(candidate_votes, reader_count)
            winner = (
                "candidate" if candidate_votes * 2 > reader_count
                else "baseline" if baseline_votes * 2 > reader_count
                else "tie"
            )
            arm_hashes = {arm["label"]: arm["arm_sha256"] for arm in arms}
            experiment = {
                "schema": quality.EXPERIMENT_SCHEMA_V2, "chapters": 15, "stage": stage,
                "story_package_id": story_package_id,
                "preregistration": prereg, "preregistration_sha256": prereg_sha256,
                "artifacts_frozen_at": max(workflow_receipts), "observations_completed_at": human_receipt,
                "blind": True, "revealed_after_observations": True, "llm_retention_role": "proxy_only",
                "arms": arms, "blind_mapping": mapping, "human_cumulative_readers": readers,
                "allocation_sha256": quality.sha_json(allocation), "sequence_contamination_reported": True,
                "held_out": stage == "formal",
                "enrollment": {
                    "included_reader_ids": [row["reader_id"] for row in readers],
                    "excluded": [],
                    "screened": len(readers),
                },
                "effect_report": {
                    "unit": "reader", "candidate_votes": candidate_votes, "baseline_votes": baseline_votes,
                    "ties": reader_count - candidate_votes - baseline_votes,
                    "preference_rate": round(candidate_votes / reader_count, 6),
                    "confidence_method": "wilson-95", "confidence_interval": [lower, upper],
                },
                "outcome": {
                    "winner": winner,
                    "product_release_pass": False,
                    "input_fingerprint": quality.sha_json({
                        "arm_hashes": arm_hashes,
                        "reader_result_sha256s": [quality.sha_json(row) for row in reader_results],
                        "blind_mapping": mapping, "decision_rule": "strict-human-preference-majority-v2",
                    }),
                },
            }
            return experiment

        negative = make_experiment("negative", candidate_wins=False, stage="pilot", reader_count=2)
        result = quality.validate_experiment(self.write_json("p1-negative-experiment.json", negative), self.project)
        self.assertEqual(result["status"], "valid_experiment")
        self.assertEqual((result["winner"], result["product_release_pass"]), ("baseline", False))

        plurality_only = make_experiment(
            "plurality", candidate_wins=True, stage="pilot", reader_count=4,
            preference_pattern=["A", "A", "B", "tie"],
        )
        plurality_result = quality.validate_experiment(self.write_json("p1-plurality-experiment.json", plurality_only), self.project)
        self.assertEqual((plurality_result["winner"], plurality_result["product_release_pass"]), ("tie", False))

        visible_mismatch = make_experiment(
            "visible-budget-mismatch", candidate_wins=True, stage="pilot", reader_count=2,
            workflow_max_visible_by_treatment={"P0": 4500, "P1": 5000},
        )
        with self.assertRaisesRegex(quality.QualityError, "visible-character budget differs from preregistration"):
            quality.validate_experiment(self.write_json("p1-visible-budget-mismatch.json", visible_mismatch), self.project)

        formal_plan = plan_experiment("formal-self-report", stage="formal", reader_count=4)
        with self.assertRaisesRegex(quality.QualityError, "treatment start boundaries"):
            make_experiment(
                "formal-self-report", candidate_wins=True, stage="formal", reader_count=4,
                planned=formal_plan,
            )

    def test_fresh_reader_checkpoint_requires_replay_evidence(self) -> None:
        candidate = quality.sha_bytes(b"candidate-15")
        base = {"chapters": {str(number): {"revision": quality.sha_bytes(f"chapter-{number}".encode())} for number in range(1, 15)}}
        pending = {"chapter": 15, "revision": candidate}
        fingerprint = quality.reader_input_fingerprint(base, pending)
        revisions = quality.reader_revision_sequence(base, pending)
        row = reader("fresh-reader", None, chapter=15, revision=candidate, input_fingerprint=fingerprint)
        row.update({
            "cohort_type": "fresh_replay",
            "replayed_from_chapter": 1,
            "replayed_through_chapter": 15,
            "replayed_revision_hashes": revisions,
            "batch_hashes": quality.reader_batch_hashes(revisions),
        })
        normalized, state_hash = quality.validate_reader_state(
            row,
            15,
            None,
            candidate_revision=candidate,
            input_fingerprint=fingerprint,
            revision_sequence=revisions,
        )
        self.assertEqual(normalized["replayed_from_chapter"], 1)
        self.assertEqual(normalized["state_hash"], state_hash)

    def test_all_deployed_lifecycle_copies_have_runtime_dependencies(self) -> None:
        for skill in ("story-write", "story-import", "story-review"):
            scripts = ROOT / "skills" / skill / "scripts"
            for name in ("quality_lifecycle.py", "storyctl.py", "tracking_commit.py", "wordcount_core.py"):
                self.assertTrue((scripts / name).is_file(), f"{skill} missing {name}")
            module = load(f"quality_{skill.replace('-', '_')}", scripts / "quality_lifecycle.py")
            self.assertIn("rebuild", module.build_parser()._subparsers._group_actions[0].choices)


if __name__ == "__main__":
    unittest.main(verbosity=2)
