#pragma once

#include <QString>
#include <QStringList>
#include <QSqlError>

#include "../dxw/HistoryIndex.h"

namespace dxw {

class DxwHistoryCache final {
public:
    explicit DxwHistoryCache(QString appPath = QString());

    void setAppPath(const QString& appPath);
    bool reload();
    HistoryFacts lookup(const std::string& call,
                        const std::string& band,
                        const std::string& mode,
                        const std::string& entity) const;

    bool available() const noexcept { return available_; }
    bool degraded() const noexcept { return degraded_; }
    std::size_t recordCount() const noexcept { return index_.size(); }
    QStringList sourceStatus() const { return sourceStatus_; }

private:
    bool loadAdifFile(const QString& path, HistoryIndex& target, QString& status) const;
    bool loadHrdFile(const QString& path, HistoryIndex& target, QString& status) const;
    QStringList discoverHrdFiles() const;

    QString appPath_;
    HistoryIndex index_;
    bool available_{false};
    bool degraded_{false};
    QStringList sourceStatus_;
};

} // namespace dxw
