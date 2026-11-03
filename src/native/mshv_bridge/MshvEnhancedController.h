#pragma once

#include <QDateTime>
#include <QFrame>
#include <QHash>
#include <QJsonObject>
#include <QNetworkAccessManager>
#include <QSet>
#include <QStringList>
#include <QTimer>
#include <QUrl>
#include <QVector>

class QCheckBox;
class QComboBox;
class QDialog;
class QLabel;
class QLineEdit;
class QPushButton;
class QSpinBox;
class QNetworkReply;

class MshvEnhancedController final : public QFrame
{
    Q_OBJECT

public:
    explicit MshvEnhancedController(const QString &appPath, QWidget *parent = nullptr);
    ~MshvEnhancedController() override;

signals:
    void selectHuntDecode(QString allText, QString selectedCall, QString time, QString txReport, QString freq);
    void selectAutoDecode(QStringList decode);
    void ensureAutoRequested();
    void requestCq();
    void haltTxRequested();
    void skipTx1Changed(bool enabled);

public slots:
    void setStationIdentity(const QString &call, const QString &grid);
    void setBand(const QString &band);
    void setModeId(int modeId);
    void onDecode(QStringList decode);
    void onLoggedQso(QStringList qso);
    void onAdifRecord(QString adif);
    void onQsoProgress(int progress);
    void onManualTarget(QString allText, QString selectedCall, QString time, QString txReport, QString freq);

private slots:
    void toggleArm();
    void haltNow();
    void openSettings();
    void targetChanged(int);
    void intervalChanged(int);
    void qualifierChanged(int);
    void strategyChanged(int);
    void decideNow();
    void watchdogTick();
    void refreshActivitySpots();
    void networkFinished(QNetworkReply *reply);

private:
    enum Strategy { Hunt = 0, Answer = 1, Both = 2 };
    enum Target {
        Anyone = 0,
        Nearby,
        Far,
        Strongest,
        CallCq,
        PotaHunter,
        SotaHunter,
        PotaSotaHunter,
        Dxcc,
        Grid,
        ItuZone,
        CqZone,
        Icdg
    };
    enum Interval { Once = 0, Always, Daily, Weekly, Monthly };
    enum Qualifier { PerCall = 0, DifferentBands, UntilConfirmed, PerBandUntilConfirmed };

    struct Entity {
        QString country;
        QString continent;
        QString prefix;
        int cqZone = 0;
        int ituZone = 0;
        bool valid = false;
    };

    struct CtyRecord {
        QString key;
        Entity entity;
        bool exact = false;
    };

    struct Candidate {
        QString call;
        QString grid;
        QString rawMessage;
        QString decodeTime;
        QString freq;
        QString band;
        QString mode;
        QString cqModifier;
        QString potaRef;
        QString sotaRef;
        Entity entity;
        int snr = -50;
        double distanceKm = -1.0;
        bool callingCq = false;
        bool directedToUs = false;
        bool busy = false;
        bool pota = false;
        bool sota = false;
        QDateTime lastSeenUtc;
        QStringList rawDecode;
    };

    struct HistoryRow {
        QString call;
        QString band;
        QString mode;
        QString grid;
        QString country;
        int cqZone = 0;
        int ituZone = 0;
        QDateTime whenUtc;
        bool confirmed = false;
    };

    struct RetryState {
        int attempts = 0;
        QDateTime windowStartUtc;
        QDateTime bannedUntilUtc;
    };

    struct UploadJob {
        QString service;
        QByteArray body;
        QUrl url;
        QHash<QByteArray,QByteArray> headers;
        int attempts = 0;
    };

    QString appPath_;
    QString myCall_;
    QString myGrid_;
    QString myBand_;
    QString myMode_;
    Entity myEntity_;

    bool armed_ = false;
    Strategy strategy_ = Both;
    Target target_ = Anyone;
    Interval interval_ = Once;
    Qualifier qualifier_ = PerCall;

    bool callNonCq_ = false;
    bool callBusy_ = false;
    bool respectDirectedCq_ = true;
    bool skipTx1_ = false;
    bool fallbackCq_ = true;
    int retryLimit_ = 3;
    int retryWindowMinutes_ = 10;
    int retryCooldownMinutes_ = 15;
    int stationExpiryMinutes_ = 3;
    int maxQsoSeconds_ = 120;
    QStringList excludedPrefixes_;

    QString activeCall_;
    bool activeEngaged_ = false;
    QDateTime activeStartedUtc_;
    QDateTime activeLastProgressUtc_;
    int activeProgress_ = 0;
    bool manualOverride_ = false;

    QVector<CtyRecord> cty_;
    QVector<HistoryRow> history_;
    QHash<QString,Candidate> stations_;
    QHash<QString,RetryState> retries_;
    QHash<QString,QString> potaRefs_;
    QHash<QString,QString> sotaRefs_;

    QTimer decisionTimer_;
    QTimer watchdogTimer_;
    QTimer spotTimer_;

    QNetworkAccessManager network_;
    QVector<UploadJob> uploadQueue_;
    bool uploadBusy_ = false;

    // Compact command bar.
    QComboBox *strategyBox_ = nullptr;
    QComboBox *targetBox_ = nullptr;
    QComboBox *intervalBox_ = nullptr;
    QComboBox *qualifierBox_ = nullptr;
    QPushButton *armButton_ = nullptr;
    QPushButton *haltButton_ = nullptr;
    QPushButton *settingsButton_ = nullptr;
    QLabel *stateLabel_ = nullptr;
    QLabel *activeLabel_ = nullptr;

    // Settings dialog controls are created lazily.
    QDialog *settingsDialog_ = nullptr;
    QCheckBox *callNonCqBox_ = nullptr;
    QCheckBox *callBusyBox_ = nullptr;
    QCheckBox *respectDirectedBox_ = nullptr;
    QCheckBox *skipTx1Box_ = nullptr;
    QCheckBox *fallbackCqBox_ = nullptr;
    QSpinBox *retryLimitBox_ = nullptr;
    QSpinBox *retryWindowBox_ = nullptr;
    QSpinBox *retryCooldownBox_ = nullptr;
    QSpinBox *stationExpiryBox_ = nullptr;
    QSpinBox *maxQsoBox_ = nullptr;
    QLineEdit *excludedPrefixesEdit_ = nullptr;
    QCheckBox *hrdEnabledBox_ = nullptr;
    QLineEdit *hrdCallEdit_ = nullptr;
    QLineEdit *hrdCodeEdit_ = nullptr;
    QCheckBox *wrlEnabledBox_ = nullptr;
    QLineEdit *wrlApiKeyEdit_ = nullptr;
    QLineEdit *wrlLogbookEdit_ = nullptr;

    bool hrdEnabled_ = false;
    QString hrdCall_;
    QString hrdCode_;
    bool wrlEnabled_ = false;
    QString wrlApiKey_;
    QString wrlLogbookId_;

    void buildCommandBar();
    void buildSettingsDialog();
    void loadSettings();
    void saveSettings();
    void loadHistory();
    void loadCty();
    Entity resolveEntity(const QString &call) const;

    void updateStatus();
    void pruneStations();
    void scheduleDecision();
    void clearActive(const QString &reason, bool cooldown);
    void selectCandidate(const Candidate &candidate);
    bool eligible(const Candidate &candidate) const;
    bool directedCqTargetsUs(const Candidate &candidate) const;
    bool excluded(const QString &call) const;
    bool retryBanned(const QString &call) const;
    void noteAttempt(const QString &call);

    QVector<Candidate> rankedCandidates() const;
    qint64 score(const Candidate &candidate) const;
    int targetNeedLevel(const Candidate &candidate) const;
    bool targetNeeded(const Candidate &candidate) const;
    bool historyBlocks(const Candidate &candidate) const;
    bool historyMatchesPeriod(const HistoryRow &row, const Candidate &candidate, bool bandSpecific) const;
    bool achievementConfirmed(const Candidate &candidate, bool bandSpecific) const;

    static bool looksLikeCall(const QString &token);
    static bool looksLikeGrid(const QString &token);
    static QString normalizedCall(const QString &call);
    static QString adifValue(const QString &adif, const QString &field);
    static QDateTime adifTime(const QString &adif);
    static QString modeNameForId(int id);
    static bool gridToLatLon(const QString &grid, double &lat, double &lon);
    static double distanceKm(const QString &a, const QString &b);
    static QString baseCall(const QString &call);

    void enrichCandidateFromSpots(Candidate &candidate) const;
    void parsePotaReply(const QByteArray &data);
    void parseSotaReply(const QByteArray &data);

    void enqueueHrdLog(const QString &adif);
    void enqueueWrl(const QString &adif);
    void pumpUploads();
    void completeUpload(QNetworkReply *reply);
    QJsonObject wrlJsonFromAdif(const QString &adif) const;
};
