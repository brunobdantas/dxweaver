#include "DxwHistoryCache.h"

#include <QDir>
#include <QDirIterator>
#include <QFile>
#include <QFileInfo>
#include <QRegularExpression>
#include <QSqlDatabase>
#include <QSqlQuery>
#include <QSqlRecord>
#include <QVariant>
#include <QUuid>

namespace dxw {

namespace {
QString quoteIdent(QString value) {
    value.replace('"', "\"\"");
    return "\"" + value + "\"";
}

QString findColumn(const QSqlRecord& record, const QStringList& aliases) {
    for (int a = 0; a < aliases.size(); ++a) {
        for (int i = 0; i < record.count(); ++i) {
            if (record.fieldName(i).compare(aliases.at(a), Qt::CaseInsensitive) == 0)
                return record.fieldName(i);
        }
    }
    return QString();
}

bool confirmedValue(const QString& value) {
    const QString v = value.trimmed().toUpper();
    return v == "Y" || v == "YES" || v == "1" || v == "TRUE" || v == "T" || v == "C";
}

QString adifValue(const QString& chunk, const QString& name) {
    const QRegularExpression re("<" + QRegularExpression::escape(name) + ":([0-9]+)(?::[^>]*)?>([^<]*)",
                                QRegularExpression::CaseInsensitiveOption);
    const QRegularExpressionMatch match = re.match(chunk);
    if (!match.hasMatch()) return QString();
    bool ok = false;
    const int len = match.captured(1).toInt(&ok);
    if (!ok || len < 0) return QString();
    return match.captured(2).left(len).trimmed();
}

QString envPath(const char* name) {
    const QByteArray value = qgetenv(name);
    return value.isEmpty() ? QString() : QString::fromLocal8Bit(value);
}
}

DxwHistoryCache::DxwHistoryCache(QString appPath) : appPath_(appPath) {}

void DxwHistoryCache::setAppPath(const QString& appPath) {
    appPath_ = appPath;
}

HistoryFacts DxwHistoryCache::lookup(const std::string& call,
                                     const std::string& band,
                                     const std::string& mode,
                                     const std::string& entity) const {
    return index_.lookup(call, band, mode, entity);
}

bool DxwHistoryCache::loadAdifFile(const QString& path, HistoryIndex& target, QString& status) const {
    QFile file(path);
    if (!file.exists()) {
        status = "ADIF missing: " + path;
        return false;
    }
    if (!file.open(QIODevice::ReadOnly | QIODevice::Text)) {
        status = "ADIF unreadable: " + path;
        return false;
    }
    const QString text = QString::fromUtf8(file.readAll());
    file.close();
    const QStringList records = text.split(QRegularExpression("<EOR\\s*>", QRegularExpression::CaseInsensitiveOption),
                                           Qt::SkipEmptyParts);
    int added = 0;
    for (int i = 0; i < records.size(); ++i) {
        const QString call = adifValue(records.at(i), "CALL");
        if (call.isEmpty()) continue;
        HistoryRecord rec;
        rec.call = call.toUpper().toStdString();
        rec.band = adifValue(records.at(i), "BAND").toLower().toStdString();
        QString mode = adifValue(records.at(i), "MODE").toUpper();
        const QString submode = adifValue(records.at(i), "SUBMODE").toUpper();
        if (!submode.isEmpty()) mode = submode;
        if (mode.isEmpty()) mode = "FT8";
        rec.mode = mode.toStdString();
        QString entity = adifValue(records.at(i), "COUNTRY");
        if (entity.isEmpty()) entity = adifValue(records.at(i), "ENTITY");
        rec.entity = entity.toStdString();
        rec.confirmed = confirmedValue(adifValue(records.at(i), "QSL_RCVD")) ||
                        confirmedValue(adifValue(records.at(i), "LOTW_QSL_RCVD")) ||
                        confirmedValue(adifValue(records.at(i), "EQSL_QSL_RCVD")) ||
                        confirmedValue(adifValue(records.at(i), "QRZCOM_QSO_UPLOAD_STATUS"));
        target.add(rec);
        ++added;
    }
    status = QString("ADIF %1: %2 records").arg(QFileInfo(path).fileName()).arg(added);
    return added > 0;
}

QStringList DxwHistoryCache::discoverHrdFiles() const {
    QStringList roots;
    const QString appData = envPath("APPDATA");
    const QString localAppData = envPath("LOCALAPPDATA");
    const QString userProfile = envPath("USERPROFILE");
    if (!appData.isEmpty()) roots << QDir(appData).filePath("HRDLLC");
    if (!localAppData.isEmpty()) roots << QDir(localAppData).filePath("HRDLLC");
    if (!userProfile.isEmpty()) {
        roots << QDir(userProfile).filePath("Documents/HRD Logbook")
              << QDir(userProfile).filePath("Documents/Ham Radio Deluxe");
    }

    const QStringList filters = QStringList() << "*.hrdsql" << "*.sqlite" << "*.sqlite3" << "*.db";
    QStringList files;
    for (int r = 0; r < roots.size(); ++r) {
        if (!QDir(roots.at(r)).exists()) continue;
        QDirIterator it(roots.at(r), filters, QDir::Files, QDirIterator::Subdirectories);
        int count = 0;
        while (it.hasNext() && count < 100) {
            const QString path = QFileInfo(it.next()).canonicalFilePath();
            if (!path.isEmpty() && !files.contains(path, Qt::CaseInsensitive)) files << path;
            ++count;
        }
    }
    return files;
}

bool DxwHistoryCache::loadHrdFile(const QString& path, HistoryIndex& target, QString& status) const {
    if (!QFileInfo::exists(path)) {
        status = "HRD missing: " + path;
        return false;
    }

    const QString connectionName = "dxw_hrd_" + QUuid::createUuid().toString(QUuid::WithoutBraces);
    bool loaded = false;
    int added = 0;
    QString errorText;
    {
        QSqlDatabase db = QSqlDatabase::addDatabase("QSQLITE", connectionName);
        db.setDatabaseName(path);
        db.setConnectOptions("QSQLITE_OPEN_READONLY;QSQLITE_BUSY_TIMEOUT=1000");
        if (!db.open()) {
            errorText = db.lastError().text();
        } else {
            const QStringList tables = db.tables(QSql::Tables);
            QString bestTable;
            QSqlRecord bestRecord;
            int bestScore = -1;
            for (int t = 0; t < tables.size(); ++t) {
                const QSqlRecord record = db.record(tables.at(t));
                const QString callCol = findColumn(record, QStringList() << "COL_CALL" << "CALL" << "CALLSIGN" << "DX_CALL");
                if (callCol.isEmpty()) continue;
                int score = record.count();
                if (tables.at(t).compare("TABLE_HRD_CONTACTS_V01", Qt::CaseInsensitive) == 0) score += 1000;
                if (score > bestScore) {
                    bestScore = score;
                    bestTable = tables.at(t);
                    bestRecord = record;
                }
            }

            if (bestTable.isEmpty()) {
                errorText = "no HRD QSO table with recognizable callsign column";
            } else {
                const QString callCol = findColumn(bestRecord, QStringList() << "COL_CALL" << "CALL" << "CALLSIGN" << "DX_CALL");
                const QString bandCol = findColumn(bestRecord, QStringList() << "COL_BAND" << "BAND");
                const QString modeCol = findColumn(bestRecord, QStringList() << "COL_MODE" << "MODE" << "SUBMODE");
                const QString countryCol = findColumn(bestRecord, QStringList() << "COL_COUNTRY" << "COUNTRY" << "ENTITY" << "DXCC_NAME");
                const QString qslCol = findColumn(bestRecord, QStringList() << "COL_QSL_RCVD" << "QSL_RCVD");
                const QString lotwCol = findColumn(bestRecord, QStringList() << "COL_LOTW_QSL_RCVD" << "LOTW_QSL_RCVD" << "LOTW_RCVD");
                const QString eqslCol = findColumn(bestRecord, QStringList() << "COL_EQSL_QSL_RCVD" << "EQSL_QSL_RCVD" << "EQSL_RCVD");

                QStringList columns;
                columns << callCol;
                if (!bandCol.isEmpty()) columns << bandCol;
                if (!modeCol.isEmpty()) columns << modeCol;
                if (!countryCol.isEmpty()) columns << countryCol;
                if (!qslCol.isEmpty()) columns << qslCol;
                if (!lotwCol.isEmpty()) columns << lotwCol;
                if (!eqslCol.isEmpty()) columns << eqslCol;

                QStringList quoted;
                for (int c = 0; c < columns.size(); ++c) quoted << quoteIdent(columns.at(c));
                QSqlQuery query(db);
                if (!query.exec("SELECT " + quoted.join(',') + " FROM " + quoteIdent(bestTable))) {
                    errorText = query.lastError().text();
                } else {
                    while (query.next()) {
                        int idx = 0;
                        HistoryRecord rec;
                        rec.call = query.value(idx++).toString().trimmed().toUpper().toStdString();
                        if (!bandCol.isEmpty()) rec.band = query.value(idx++).toString().trimmed().toLower().toStdString();
                        if (!modeCol.isEmpty()) rec.mode = query.value(idx++).toString().trimmed().toUpper().toStdString();
                        if (rec.mode.empty()) rec.mode = "FT8";
                        if (!countryCol.isEmpty()) rec.entity = query.value(idx++).toString().trimmed().toStdString();
                        bool confirmed = false;
                        if (!qslCol.isEmpty()) confirmed = confirmed || confirmedValue(query.value(idx++).toString());
                        if (!lotwCol.isEmpty()) confirmed = confirmed || confirmedValue(query.value(idx++).toString());
                        if (!eqslCol.isEmpty()) confirmed = confirmed || confirmedValue(query.value(idx++).toString());
                        rec.confirmed = confirmed;
                        target.add(rec);
                        ++added;
                    }
                    loaded = added > 0;
                }
            }
            db.close();
        }
    }
    QSqlDatabase::removeDatabase(connectionName);

    if (loaded) {
        status = QString("HRD %1: %2 records").arg(QFileInfo(path).fileName()).arg(added);
        return true;
    }
    status = QString("HRD degraded %1: %2").arg(QFileInfo(path).fileName(), errorText);
    return false;
}

bool DxwHistoryCache::reload() {
    HistoryIndex next;
    QStringList statuses;
    bool any = false;
    bool failure = false;

    if (!appPath_.isEmpty()) {
        QString status;
        const QString localAdif = QDir(appPath_).filePath("log/mshvlog.adi");
        if (QFileInfo::exists(localAdif)) {
            const bool ok = loadAdifFile(localAdif, next, status);
            any = any || ok;
            failure = failure || !ok;
            statuses << status;
        }
    }

    const QStringList hrdFiles = discoverHrdFiles();
    for (int i = 0; i < hrdFiles.size(); ++i) {
        QString status;
        const bool ok = loadHrdFile(hrdFiles.at(i), next, status);
        any = any || ok;
        failure = failure || !ok;
        statuses << status;
    }

    index_ = next;
    available_ = any && index_.size() > 0;
    degraded_ = failure || !available_;
    sourceStatus_ = statuses;
    if (sourceStatus_.isEmpty()) sourceStatus_ << "history unavailable: CTY/SNR fallback active";
    return available_;
}

} // namespace dxw
