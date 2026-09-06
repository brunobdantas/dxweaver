#pragma once

#include "HistoryIndex.h"
#include <memory>
#include <string>

namespace dxw {

class IHistoryProvider {
public:
    virtual ~IHistoryProvider() {}
    virtual bool lookup(const std::string& call,
                        const std::string& band,
                        const std::string& mode,
                        const std::string& entity,
                        HistoryFacts& facts) const noexcept = 0;
};

class ResilientHistoryProvider final : public IHistoryProvider {
public:
    explicit ResilientHistoryProvider(std::shared_ptr<const IHistoryProvider> primary)
        : primary_(primary) {}

    bool lookup(const std::string& call,
                const std::string& band,
                const std::string& mode,
                const std::string& entity,
                HistoryFacts& facts) const noexcept override {
        facts = HistoryFacts();
        if (!primary_) return false;
        HistoryFacts candidate;
        if (!primary_->lookup(call, band, mode, entity, candidate)) return false;
        facts = candidate;
        return true;
    }

private:
    std::shared_ptr<const IHistoryProvider> primary_;
};

} // namespace dxw
