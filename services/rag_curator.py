"""RAG-based policy curation."""

from __future__ import annotations

from collections import defaultdict

from models.rag_schemas import CuratedPolicyRecommendation, RetrievedEvidence
from models.schemas import BusinessCase, EligibilityResult
from utils.constants import CAUTION_MESSAGE

STATUS_SCORE = {
    "검토 가능": 0.9,
    "조건부 검토": 0.65,
    "판단 보류": 0.4,
    "제외 가능성": 0.2,
}


def _group_evidence_by_title(evidence: list[RetrievedEvidence]) -> dict[str, list[RetrievedEvidence]]:
    groups: dict[str, list[RetrievedEvidence]] = defaultdict(list)
    for ev in evidence:
        groups[ev.title].append(ev)
    return groups


def _match_eligibility(policy_name: str, results: list[EligibilityResult]) -> EligibilityResult | None:
    for r in results:
        if r.policy_name in policy_name or policy_name in r.policy_name:
            return r
        # match by removing [데모] prefix
        clean_r = r.policy_name.replace("[데모] ", "")
        clean_p = policy_name.replace("[데모] ", "")
        if clean_r in clean_p or clean_p in clean_r:
            return r
    return None


def curate_top_policies(
    case: BusinessCase,
    eligibility_results: list[EligibilityResult],
    retrieved_evidence: list[RetrievedEvidence],
    top_n: int = 3,
) -> list[CuratedPolicyRecommendation]:
    ev_by_title = _group_evidence_by_title(retrieved_evidence)
    candidates: list[dict] = []

    # Combine eligibility results with RAG evidence
    seen_titles: set[str] = set()
    for er in eligibility_results:
        title = er.policy_name
        seen_titles.add(title)
        evs = ev_by_title.get(title, [])
        if not evs:
            # fuzzy match evidence by institution or partial title
            for t, ev_list in ev_by_title.items():
                if er.institution and er.institution in t:
                    evs = ev_list
                    break
        rag_score = max((e.score for e in evs), default=0.3)
        status_score = STATUS_SCORE.get(er.final_status, 0.4)
        fit = round(min(0.99, status_score * 0.7 + rag_score * 0.3), 2)

        matched = [c.reason for c in er.condition_results if c.result == "충족"]
        missing = er.missing_fields + [c.condition_name for c in er.condition_results if c.result in ("미확인", "추가 확인 필요")]
        exclusions = er.exclusion_reasons

        why = []
        if matched:
            why.append(f"다음 조건이 충족 또는 일치: {', '.join(matched[:3])}")
        if evs:
            why.append(f"정책 문서 근거 {len(evs)}건 검색됨")
        if er.final_status == "검토 가능":
            why.append("규칙 엔진 기준 핵심 조건 충족")
        if not why:
            why.append("상담 케이스와 정책 문서 연관성 기반 후보")

        candidates.append({
            "policy_name": title,
            "institution": er.institution,
            "fit_score": fit,
            "review_status": er.final_status,
            "why_recommended": why,
            "matched_conditions": matched,
            "missing_or_uncertain_conditions": list(dict.fromkeys(missing)),
            "exclusion_risks": exclusions,
            "required_documents": er.required_documents,
            "next_actions": er.next_actions or [f"{m} 확인" for m in missing[:3]],
            "evidence": evs[:5],
            "eligibility": er,
        })

    # Add RAG-only candidates not in eligibility
    for title, evs in ev_by_title.items():
        if any(title in c["policy_name"] or c["policy_name"] in title for c in candidates):
            continue
        rag_score = max(e.score for e in evs)
        institution = evs[0].source_name or "미확인"
        candidates.append({
            "policy_name": title,
            "institution": institution or "미확인",
            "fit_score": round(rag_score * 0.6, 2),
            "review_status": "판단 보류",
            "why_recommended": [f"정책 문서 검색 점수 기반 후보 (문서 {len(evs)}건)"],
            "matched_conditions": [],
            "missing_or_uncertain_conditions": ["조건검토 엔진 매칭 필요"],
            "exclusion_risks": [],
            "required_documents": [],
            "next_actions": ["정책 조건 상세 확인"],
            "evidence": evs[:5],
            "eligibility": None,
        })

    candidates.sort(key=lambda x: x["fit_score"], reverse=True)

    recommendations: list[CuratedPolicyRecommendation] = []
    for rank, c in enumerate(candidates[:top_n], 1):
        recommendations.append(
            CuratedPolicyRecommendation(
                policy_name=c["policy_name"],
                institution=c["institution"],
                priority_rank=rank,
                fit_score=c["fit_score"],
                review_status=c["review_status"],
                why_recommended=c["why_recommended"],
                matched_conditions=c["matched_conditions"],
                missing_or_uncertain_conditions=c["missing_or_uncertain_conditions"],
                exclusion_risks=c["exclusion_risks"],
                required_documents=c["required_documents"],
                next_actions=c["next_actions"],
                evidence=c["evidence"],
                caution_message=CAUTION_MESSAGE,
            )
        )
    return recommendations
