#pragma once

#include "Domain.h"
#include <vector>

namespace dxw {

struct ScoreWeights {
    int newDxcc{4000};
    int newBand{150};
    int newMode{100};
    int newSlot{80};
    int lotw{25};
    int eqsl{10};
    int watchlist{500};
    int unconfirmed{200};
    int workedPenalty{-150};
    int cooldownPenalty{-2500};
    int snrPerDb{2};
    int distancePer1000Km{2};
};

class CandidateScorer final {
public:
    explicit CandidateScorer(ScoreWeights weights = {});

    ScoreBreakdown score(const Candidate& candidate) const noexcept;
    std::vector<RankedCandidate> rank(const std::vector<Candidate>& candidates) const;

private:
    ScoreWeights weights_;
};

} // namespace dxw
