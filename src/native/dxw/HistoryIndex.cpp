#include "HistoryIndex.h"

#include <algorithm>
#include <cctype>

namespace dxw {

namespace {
char toUpperChar(char c) { return static_cast<char>(std::toupper(static_cast<unsigned char>(c))); }
char toLowerChar(char c) { return static_cast<char>(std::tolower(static_cast<unsigned char>(c))); }
}

std::string HistoryIndex::upper(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), toUpperChar);
    return value;
}

std::string HistoryIndex::lower(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), toLowerChar);
    return value;
}

std::string HistoryIndex::entityKey(std::string value) {
    return lower(value);
}

std::string HistoryIndex::pairKey(const std::string& a, const std::string& b) {
    return a + "\x1f" + b;
}

std::string HistoryIndex::slotKey(const std::string& a, const std::string& b, const std::string& c) {
    return a + "\x1f" + b + "\x1f" + c;
}

void HistoryIndex::clear() {
    calls_.clear();
    callBands_.clear();
    callModes_.clear();
    callSlots_.clear();
    confirmedCalls_.clear();
    entities_.clear();
    entityBands_.clear();
    entityModes_.clear();
    entitySlots_.clear();
    recordCount_ = 0;
}

void HistoryIndex::add(const HistoryRecord& record) {
    const std::string call = upper(record.call);
    const std::string band = lower(record.band);
    const std::string mode = upper(record.mode.empty() ? "FT8" : record.mode);
    const std::string entity = entityKey(record.entity);
    if (call.empty()) return;

    calls_.insert(call);
    if (!band.empty()) callBands_.insert(pairKey(call, band));
    if (!mode.empty()) callModes_.insert(pairKey(call, mode));
    if (!band.empty() && !mode.empty()) callSlots_.insert(slotKey(call, band, mode));
    if (record.confirmed) confirmedCalls_.insert(call);

    if (!entity.empty()) {
        entities_.insert(entity);
        if (!band.empty()) entityBands_.insert(pairKey(entity, band));
        if (!mode.empty()) entityModes_.insert(pairKey(entity, mode));
        if (!band.empty() && !mode.empty()) entitySlots_.insert(slotKey(entity, band, mode));
    }
    ++recordCount_;
}

HistoryFacts HistoryIndex::lookup(const std::string& callValue,
                                  const std::string& bandValue,
                                  const std::string& modeValue,
                                  const std::string& entityValue) const {
    HistoryFacts facts;
    const std::string call = upper(callValue);
    const std::string band = lower(bandValue);
    const std::string mode = upper(modeValue.empty() ? "FT8" : modeValue);
    const std::string entity = entityKey(entityValue);

    facts.worked = calls_.count(call) != 0;
    facts.confirmed = confirmedCalls_.count(call) != 0;
    facts.workedBand = !band.empty() && callBands_.count(pairKey(call, band)) != 0;
    facts.workedMode = !mode.empty() && callModes_.count(pairKey(call, mode)) != 0;
    facts.workedSlot = !band.empty() && !mode.empty() && callSlots_.count(slotKey(call, band, mode)) != 0;

    if (!entity.empty()) {
        facts.entityWorked = entities_.count(entity) != 0;
        facts.entityBandWorked = !band.empty() && entityBands_.count(pairKey(entity, band)) != 0;
        facts.entityModeWorked = !mode.empty() && entityModes_.count(pairKey(entity, mode)) != 0;
        facts.entitySlotWorked = !band.empty() && !mode.empty() && entitySlots_.count(slotKey(entity, band, mode)) != 0;
    }
    return facts;
}

} // namespace dxw
