#pragma once

#include <set>
#include <string>

namespace dxw {

struct HistoryRecord {
    std::string call;
    std::string band;
    std::string mode;
    std::string entity;
    bool confirmed{false};
};

struct HistoryFacts {
    bool worked{false};
    bool confirmed{false};
    bool workedBand{false};
    bool workedMode{false};
    bool workedSlot{false};
    bool entityWorked{false};
    bool entityBandWorked{false};
    bool entityModeWorked{false};
    bool entitySlotWorked{false};
};

class HistoryIndex final {
public:
    void clear();
    void add(const HistoryRecord& record);
    HistoryFacts lookup(const std::string& call,
                        const std::string& band,
                        const std::string& mode,
                        const std::string& entity) const;
    std::size_t size() const noexcept { return recordCount_; }

private:
    static std::string upper(std::string value);
    static std::string lower(std::string value);
    static std::string entityKey(std::string value);
    static std::string pairKey(const std::string& a, const std::string& b);
    static std::string slotKey(const std::string& a, const std::string& b, const std::string& c);

    std::set<std::string> calls_;
    std::set<std::string> callBands_;
    std::set<std::string> callModes_;
    std::set<std::string> callSlots_;
    std::set<std::string> confirmedCalls_;
    std::set<std::string> entities_;
    std::set<std::string> entityBands_;
    std::set<std::string> entityModes_;
    std::set<std::string> entitySlots_;
    std::size_t recordCount_{0};
};

} // namespace dxw
