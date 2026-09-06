#pragma once

#include <cstddef>
#include <string>
#include <vector>

namespace dxw {

struct CtyEntity {
    bool found{false};
    std::string prefix;
    std::string country;
    std::string continent;
    int cqZone{0};
    int ituZone{0};
    double latitude{0.0};
    double longitude{0.0};
};

class CtyResolver final {
public:
    bool load(const std::string& path);
    bool resolve(const std::string& callsign, CtyEntity& result) const;
    std::size_t size() const noexcept { return records_.size(); }

private:
    struct Record {
        std::string key;
        CtyEntity entity;
        bool exact{false};
    };

    static std::string trim(const std::string& value);
    static std::string upper(std::string value);
    static std::vector<std::string> split(const std::string& value, char separator);
    static bool extractOverride(std::string& token, char open, char close, int& value);
    static std::vector<std::string> lookupForms(const std::string& callsign);
    static bool longerKeyFirst(const Record& a, const Record& b);

    std::vector<Record> records_;
};

} // namespace dxw
