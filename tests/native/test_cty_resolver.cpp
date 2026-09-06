#include <gtest/gtest.h>
#include "dxw/CtyResolver.h"

#include <cstdio>
#include <fstream>

using namespace dxw;

TEST(CtyResolver, ResolvesPrimaryPrefixAndExactZoneOverrides) {
    const char* path = "dxw_test_cty.dat";
    {
        std::ofstream out(path, std::ios::out | std::ios::trunc);
        ASSERT_TRUE(out.good());
        out << "Trinidad & Tobago: 09: 11: SA: 10.50: 61.30: 4.0: 9Y: =9Y4ZZ(08)[10],9Y4;\n";
        out << "Argentina: 13: 14: SA: -34.00: 64.00: 3.0: LU:;\n";
    }

    CtyResolver resolver;
    ASSERT_TRUE(resolver.load(path));

    CtyEntity normal;
    ASSERT_TRUE(resolver.resolve("9Y4C", normal));
    EXPECT_EQ(normal.country, "Trinidad & Tobago");
    EXPECT_EQ(normal.continent, "SA");
    EXPECT_EQ(normal.cqZone, 9);
    EXPECT_EQ(normal.ituZone, 11);

    CtyEntity exact;
    ASSERT_TRUE(resolver.resolve("9Y4ZZ", exact));
    EXPECT_EQ(exact.country, "Trinidad & Tobago");
    EXPECT_EQ(exact.cqZone, 8);
    EXPECT_EQ(exact.ituZone, 10);

    CtyEntity argentina;
    ASSERT_TRUE(resolver.resolve("LU2DPG", argentina));
    EXPECT_EQ(argentina.country, "Argentina");
    EXPECT_EQ(argentina.cqZone, 13);
    EXPECT_EQ(argentina.ituZone, 14);

    std::remove(path);
}

TEST(CtyResolver, MissingDatabaseFailsClosedWithoutInventingEntity) {
    CtyResolver resolver;
    EXPECT_FALSE(resolver.load("this-file-must-not-exist.cty"));
    CtyEntity result;
    EXPECT_FALSE(resolver.resolve("9Y4C", result));
    EXPECT_FALSE(result.found);
}
