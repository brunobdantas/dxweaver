#include "CandidateScorer.h"
#include <algorithm>
#include <cmath>

namespace dxw {
namespace {

template <typename T>
T clampValue(T value, T low, T high) {
    return std::max(low, std::min(value, high));
}

} // namespace

CandidateScorer::CandidateScorer(ScoreWeights weights) : weights_(weights) {}

ScoreBreakdown CandidateScorer::score(const Candidate& c) const noexcept {
    ScoreBreakdown s;
    s.newDxcc = c.newDxcc ? weights_.newDxcc : 0;
    s.newBand = c.newBand ? weights_.newBand : 0;
    s.newMode = c.newMode ? weights_.newMode : 0;
    s.newSlot = c.newSlot ? weights_.newSlot : 0;
    s.lotw = c.lotw ? weights_.lotw : 0;
    s.eqsl = c.eqsl ? weights_.eqsl : 0;
    s.watchlist = c.watchlist ? weights_.watchlist : 0;
    s.unconfirmed = (!c.confirmed && c.worked) ? weights_.unconfirmed : 0;

    const int normalizedSnr = clampValue(c.snr + 30, 0, 50);
    s.snr = normalizedSnr * weights_.snrPerDb;

    const double normalizedDistance = clampValue(c.distanceKm / 1000.0, 0.0, 20.0);
    const int distanceBuckets = static_cast<int>(normalizedDistance);
    s.distance = distanceBuckets * weights_.distancePer1000Km;

    s.workedPenalty = (c.worked && c.confirmed) ? weights_.workedPenalty : 0;
    s.cooldownPenalty = c.cooldownActive ? weights_.cooldownPenalty : 0;

    s.total = s.newDxcc + s.newBand + s.newMode + s.newSlot + s.lotw + s.eqsl +
              s.watchlist + s.unconfirmed + s.snr + s.distance +
              s.workedPenalty + s.cooldownPenalty;
    return s;
}

std::vector<RankedCandidate> CandidateScorer::rank(const std::vector<Candidate>& candidates) const {
    std::vector<RankedCandidate> ranked;
    ranked.reserve(candidates.size());
    for (const auto& c : candidates) ranked.push_back({c, score(c)});
    std::stable_sort(ranked.begin(), ranked.end(), [](const RankedCandidate& a, const RankedCandidate& b) {
        if (a.score.total != b.score.total) return a.score.total > b.score.total;
        if (a.candidate.snr != b.candidate.snr) return a.candidate.snr > b.candidate.snr;
        return a.candidate.call < b.candidate.call;
    });
    return ranked;
}

} // namespace dxw
