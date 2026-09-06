#include <gtest/gtest.h>
#include "dxw/HistoryIndex.h"

using namespace dxw;

TEST(HistoryIndex, DistinguishesCallEntityBandModeAndSlotNovelty) {
    HistoryIndex index;
    HistoryRecord old;
    old.call = "9Y4OLD";
    old.band = "20m";
    old.mode = "FT8";
    old.entity = "Trinidad & Tobago";
    old.confirmed = true;
    index.add(old);

    HistoryFacts exact = index.lookup("9Y4OLD", "20m", "FT8", "Trinidad & Tobago");
    EXPECT_TRUE(exact.worked);
    EXPECT_TRUE(exact.confirmed);
    EXPECT_TRUE(exact.workedBand);
    EXPECT_TRUE(exact.workedMode);
    EXPECT_TRUE(exact.workedSlot);
    EXPECT_TRUE(exact.entityWorked);
    EXPECT_TRUE(exact.entityBandWorked);
    EXPECT_TRUE(exact.entityModeWorked);
    EXPECT_TRUE(exact.entitySlotWorked);

    HistoryFacts newCallSameEntity = index.lookup("9Y4C", "15m", "FT8", "Trinidad & Tobago");
    EXPECT_FALSE(newCallSameEntity.worked);
    EXPECT_TRUE(newCallSameEntity.entityWorked);
    EXPECT_FALSE(newCallSameEntity.entityBandWorked);
    EXPECT_TRUE(newCallSameEntity.entityModeWorked);
    EXPECT_FALSE(newCallSameEntity.entitySlotWorked);

    HistoryFacts newEntity = index.lookup("LU1AAA", "15m", "FT8", "Argentina");
    EXPECT_FALSE(newEntity.worked);
    EXPECT_FALSE(newEntity.entityWorked);
    EXPECT_FALSE(newEntity.entityBandWorked);
    EXPECT_FALSE(newEntity.entityModeWorked);
    EXPECT_FALSE(newEntity.entitySlotWorked);
}

TEST(HistoryIndex, EmptyIndexIsDeterministicAndDoesNotThrow) {
    HistoryIndex index;
    const HistoryFacts facts = index.lookup("9Y4C", "15m", "FT8", "Trinidad & Tobago");
    EXPECT_FALSE(facts.worked);
    EXPECT_FALSE(facts.confirmed);
    EXPECT_FALSE(facts.entityWorked);
    EXPECT_EQ(index.size(), 0u);
}
