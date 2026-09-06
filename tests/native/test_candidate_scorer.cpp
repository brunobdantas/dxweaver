#include <gtest/gtest.h>
#include "dxw/CandidateScorer.h"
#include <chrono>

using namespace dxw;

TEST(CandidateScorer, NewDxccDominatesOrdinaryWorkedStation) {
    CandidateScorer scorer;
    Candidate rare; rare.call="9Y4C"; rare.snr=-18; rare.newDxcc=true; rare.newBand=true;
    Candidate loud; loud.call="EA2EED"; loud.snr=12; loud.worked=true; loud.confirmed=true;
    auto ranked = scorer.rank({loud, rare});
    ASSERT_EQ(ranked.size(), 2u);
    EXPECT_EQ(ranked.front().candidate.call, "9Y4C");
    EXPECT_GT(ranked.front().score.total, ranked.back().score.total);
}

TEST(CandidateScorer, CooldownAppliesStrongPenalty) {
    CandidateScorer scorer;
    Candidate a; a.call="9Y4C"; a.newDxcc=true; a.cooldownActive=true; a.snr=-5;
    auto sa = scorer.score(a);
    EXPECT_EQ(sa.cooldownPenalty, -2500);
}

TEST(CandidateScorer, OneHundredTwentyCandidatesRemainBelowFiveMilliseconds) {
    CandidateScorer scorer;
    std::vector<Candidate> batch;
    batch.reserve(120);
    for (int i=0; i<120; ++i) {
        Candidate c;
        c.call = "T" + std::to_string(i) + "ABC";
        c.snr = -30 + (i % 45);
        c.distanceKm = 100.0 * i;
        c.newDxcc = (i % 31 == 0);
        c.newBand = (i % 7 == 0);
        c.newMode = (i % 11 == 0);
        c.newSlot = (i % 5 == 0);
        c.worked = (i % 3 == 0);
        c.confirmed = (i % 6 == 0);
        batch.push_back(c);
    }

    for (int i=0; i<20; ++i) (void)scorer.rank(batch);
    const auto start = std::chrono::steady_clock::now();
    for (int i=0; i<100; ++i) (void)scorer.rank(batch);
    const auto elapsed = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now()-start).count();
    const double perBatchMs = elapsed / 100.0;
    EXPECT_LT(perBatchMs, 5.0) << "120-decode scoring batch took " << perBatchMs << " ms";
}
