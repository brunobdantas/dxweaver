#include "MshvEnhancedController.h"

#include <QCheckBox>
#include <QComboBox>
#include <QCoreApplication>
#include <QDialog>
#include <QDialogButtonBox>
#include <QFile>
#include <QFormLayout>
#include <QGroupBox>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QJsonDocument>
#include <QLabel>
#include <QLineEdit>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QPushButton>
#include <QRegularExpression>
#include <QSettings>
#include <QSpinBox>
#include <QUrlQuery>
#include <QVBoxLayout>

#include <algorithm>
#include <cmath>

namespace {

QString upperTrimmed(const QString &s)
{
    return s.trimmed().toUpper();
}

QString normalizeBandName(const QString &value)
{
    const QString b = value.trimmed().toUpper();
    static const QHash<QString,QString> map = {
        {"135 KHZ","2190M"}, {"472 KHZ","630M"}, {"501 KHZ","560M"},
        {"1.8 MHZ","160M"}, {"3.5 MHZ","80M"}, {"5 MHZ","60M"},
        {"7 MHZ","40M"}, {"10 MHZ","30M"}, {"14 MHZ","20M"},
        {"18 MHZ","17M"}, {"21 MHZ","15M"}, {"24 MHZ","12M"},
        {"27 MHZ","11M"}, {"28 MHZ","10M"}, {"40 MHZ","8M"},
        {"50 MHZ","6M"}, {"60 MHZ","5M"}, {"70 MHZ","4M"},
        {"144 MHZ","2M"}, {"222 MHZ","1.25M"}, {"432 MHZ","70CM"},
        {"902 MHZ","33CM"}, {"1296 MHZ","23CM"}, {"2320 MHZ","13CM"},
        {"3.4 GHZ","9CM"}, {"5.65 GHZ","6CM"}, {"10 GHZ","3CM"},
        {"24 GHZ","1.25CM"}, {"47 GHZ","6MM"}, {"76 GHZ","4MM"},
        {"120 GHZ","2.5MM"}, {"144 GHZ","2MM"}, {"248 GHZ","1MM"}
    };
    return map.value(b, b);
}

bool truthyAdif(const QString &s)
{
    const QString v = s.trimmed().toUpper();
    return v == "Y" || v == "C" || v == "V";
}

QString jsonString(const QJsonObject &o, const char *a, const char *b = nullptr, const char *c = nullptr)
{
    QString value = o.value(QString::fromLatin1(a)).toString();
    if (value.isEmpty() && b) value = o.value(QString::fromLatin1(b)).toString();
    if (value.isEmpty() && c) value = o.value(QString::fromLatin1(c)).toString();
    return value;
}

} // namespace

MshvEnhancedController::MshvEnhancedController(const QString &appPath, QWidget *parent)
    : QFrame(parent),
      appPath_(appPath)
{
    setObjectName("mshvEnhancedBar");
    setFrameShape(QFrame::StyledPanel);

    loadSettings();
    loadCty();
    loadHistory();
    buildCommandBar();

    decisionTimer_.setSingleShot(true);
    decisionTimer_.setInterval(650);
    connect(&decisionTimer_, SIGNAL(timeout()), this, SLOT(decideNow()));

    watchdogTimer_.setInterval(1000);
    connect(&watchdogTimer_, SIGNAL(timeout()), this, SLOT(watchdogTick()));
    watchdogTimer_.start();

    spotTimer_.setInterval(60000);
    connect(&spotTimer_, SIGNAL(timeout()), this, SLOT(refreshActivitySpots()));
    spotTimer_.start();
    QTimer::singleShot(1500, this, SLOT(refreshActivitySpots()));

    connect(&network_, SIGNAL(finished(QNetworkReply*)), this, SLOT(networkFinished(QNetworkReply*)));

    updateStatus();
}

MshvEnhancedController::~MshvEnhancedController()
{
    saveSettings();
}

void MshvEnhancedController::buildCommandBar()
{
    QHBoxLayout *row = new QHBoxLayout(this);
    row->setContentsMargins(5, 2, 5, 2);
    row->setSpacing(4);

    QLabel *title = new QLabel(tr("MSHV Enhanced AUTO"), this);
    QFont tf = title->font();
    tf.setBold(true);
    title->setFont(tf);
    row->addWidget(title);

    strategyBox_ = new QComboBox(this);
    strategyBox_->addItems(QStringList() << "HUNT" << "ANSWER" << "BOTH");
    strategyBox_->setCurrentIndex(static_cast<int>(strategy_));
    strategyBox_->setToolTip(tr("HUNT calls targets; ANSWER only answers directed callers; BOTH does both."));
    connect(strategyBox_, SIGNAL(currentIndexChanged(int)), this, SLOT(strategyChanged(int)));
    row->addWidget(strategyBox_);

    targetBox_ = new QComboBox(this);
    targetBox_->addItems(QStringList()
        << tr("Anyone")
        << tr("Nearby")
        << tr("Far")
        << tr("Signal strength")
        << tr("Call CQ")
        << tr("POTA hunter")
        << tr("SOTA hunter")
        << tr("POTA + SOTA")
        << "DXCC"
        << tr("Grid")
        << tr("ITU zone")
        << tr("CQ zone")
        << "I/C/D/G");
    targetBox_->setCurrentIndex(static_cast<int>(target_));
    connect(targetBox_, SIGNAL(currentIndexChanged(int)), this, SLOT(targetChanged(int)));
    row->addWidget(targetBox_);

    intervalBox_ = new QComboBox(this);
    intervalBox_->addItems(QStringList() << tr("Once") << tr("Always") << tr("Daily") << tr("Weekly") << tr("Monthly"));
    intervalBox_->setCurrentIndex(static_cast<int>(interval_));
    connect(intervalBox_, SIGNAL(currentIndexChanged(int)), this, SLOT(intervalChanged(int)));
    row->addWidget(intervalBox_);

    qualifierBox_ = new QComboBox(this);
    qualifierBox_->addItems(QStringList()
        << tr("Per callsign")
        << tr("Different bands")
        << tr("Until target confirmed")
        << tr("Per band + until confirmed"));
    qualifierBox_->setCurrentIndex(static_cast<int>(qualifier_));
    connect(qualifierBox_, SIGNAL(currentIndexChanged(int)), this, SLOT(qualifierChanged(int)));
    row->addWidget(qualifierBox_);

    armButton_ = new QPushButton(tr("ARM"), this);
    armButton_->setCheckable(true);
    connect(armButton_, SIGNAL(clicked()), this, SLOT(toggleArm()));
    row->addWidget(armButton_);

    haltButton_ = new QPushButton(tr("HALT TX"), this);
    connect(haltButton_, SIGNAL(clicked()), this, SLOT(haltNow()));
    row->addWidget(haltButton_);

    settingsButton_ = new QPushButton(tr("Enhanced Settings"), this);
    connect(settingsButton_, SIGNAL(clicked()), this, SLOT(openSettings()));
    row->addWidget(settingsButton_);

    stateLabel_ = new QLabel(this);
    activeLabel_ = new QLabel(this);
    row->addWidget(stateLabel_);
    row->addWidget(activeLabel_);
    row->addStretch(1);
}

void MshvEnhancedController::buildSettingsDialog()
{
    if (settingsDialog_) return;

    settingsDialog_ = new QDialog(this);
    settingsDialog_->setWindowTitle(tr("MSHV Enhanced Settings"));
    QVBoxLayout *root = new QVBoxLayout(settingsDialog_);

    QGroupBox *autoGroup = new QGroupBox(tr("AUTO operation"), settingsDialog_);
    QFormLayout *autoForm = new QFormLayout(autoGroup);

    callNonCqBox_ = new QCheckBox(tr("Call stations even if they did not call CQ"), autoGroup);
    callBusyBox_ = new QCheckBox(tr("Call stations even if they appear busy"), autoGroup);
    respectDirectedBox_ = new QCheckBox(tr("Avoid directed CQs that do not target us"), autoGroup);
    skipTx1Box_ = new QCheckBox(tr("Skip Tx1 - send report first, without GRID"), autoGroup);
    fallbackCqBox_ = new QCheckBox(tr("Call CQ when no eligible target exists"), autoGroup);

    retryLimitBox_ = new QSpinBox(autoGroup);
    retryLimitBox_->setRange(1, 20);
    retryWindowBox_ = new QSpinBox(autoGroup);
    retryWindowBox_->setRange(1, 120);
    retryWindowBox_->setSuffix(tr(" min"));
    retryCooldownBox_ = new QSpinBox(autoGroup);
    retryCooldownBox_->setRange(1, 1440);
    retryCooldownBox_->setSuffix(tr(" min"));
    stationExpiryBox_ = new QSpinBox(autoGroup);
    stationExpiryBox_->setRange(1, 60);
    stationExpiryBox_->setSuffix(tr(" min"));
    maxQsoBox_ = new QSpinBox(autoGroup);
    maxQsoBox_->setRange(30, 900);
    maxQsoBox_->setSuffix(tr(" s"));
    excludedPrefixesEdit_ = new QLineEdit(autoGroup);
    excludedPrefixesEdit_->setPlaceholderText("e.g. ZZ, TEST, N0");

    autoForm->addRow(callNonCqBox_);
    autoForm->addRow(callBusyBox_);
    autoForm->addRow(respectDirectedBox_);
    autoForm->addRow(skipTx1Box_);
    autoForm->addRow(fallbackCqBox_);
    autoForm->addRow(tr("Retry limit:"), retryLimitBox_);
    autoForm->addRow(tr("Retry window:"), retryWindowBox_);
    autoForm->addRow(tr("Cooldown after retry limit:"), retryCooldownBox_);
    autoForm->addRow(tr("Forget silent stations after:"), stationExpiryBox_);
    autoForm->addRow(tr("Maximum stalled QSO time:"), maxQsoBox_);
    autoForm->addRow(tr("Excluded prefixes:"), excludedPrefixesEdit_);
    root->addWidget(autoGroup);

    QGroupBox *logGroup = new QGroupBox(tr("Online logging"), settingsDialog_);
    QFormLayout *logForm = new QFormLayout(logGroup);

    QLabel *club = new QLabel(tr("Club Log: use MSHV's native Club Log settings (Radio/Network configuration)."), logGroup);
    club->setWordWrap(true);
    logForm->addRow(club);

    hrdEnabledBox_ = new QCheckBox(tr("Upload every completed QSO to HRDLog.net"), logGroup);
    hrdCallEdit_ = new QLineEdit(logGroup);
    hrdCodeEdit_ = new QLineEdit(logGroup);
    hrdCodeEdit_->setEchoMode(QLineEdit::Password);
    logForm->addRow(hrdEnabledBox_);
    logForm->addRow(tr("HRDLog callsign:"), hrdCallEdit_);
    logForm->addRow(tr("HRDLog upload code:"), hrdCodeEdit_);

    wrlEnabledBox_ = new QCheckBox(tr("Upload every completed QSO to World Radio League"), logGroup);
    wrlApiKeyEdit_ = new QLineEdit(logGroup);
    wrlApiKeyEdit_->setEchoMode(QLineEdit::Password);
    wrlLogbookEdit_ = new QLineEdit(logGroup);
    wrlLogbookEdit_->setPlaceholderText(tr("optional; leave empty for account default"));
    logForm->addRow(wrlEnabledBox_);
    logForm->addRow(tr("WRL API key:"), wrlApiKeyEdit_);
    logForm->addRow(tr("WRL logbook id:"), wrlLogbookEdit_);
    root->addWidget(logGroup);

    QDialogButtonBox *buttons = new QDialogButtonBox(QDialogButtonBox::Save | QDialogButtonBox::Cancel, settingsDialog_);
    connect(buttons, SIGNAL(accepted()), settingsDialog_, SLOT(accept()));
    connect(buttons, SIGNAL(rejected()), settingsDialog_, SLOT(reject()));
    root->addWidget(buttons);
}

void MshvEnhancedController::loadSettings()
{
    QSettings s(appPath_ + "/settings/mshv_enhanced.ini", QSettings::IniFormat);
    strategy_ = static_cast<Strategy>(s.value("auto/strategy", static_cast<int>(Both)).toInt());
    target_ = static_cast<Target>(s.value("auto/target", static_cast<int>(Anyone)).toInt());
    interval_ = static_cast<Interval>(s.value("auto/interval", static_cast<int>(Once)).toInt());
    qualifier_ = static_cast<Qualifier>(s.value("auto/qualifier", static_cast<int>(PerCall)).toInt());

    callNonCq_ = s.value("auto/call_non_cq", false).toBool();
    callBusy_ = s.value("auto/call_busy", false).toBool();
    respectDirectedCq_ = s.value("auto/respect_directed_cq", true).toBool();
    skipTx1_ = s.value("auto/skip_tx1", false).toBool();
    fallbackCq_ = s.value("auto/fallback_cq", true).toBool();
    retryLimit_ = s.value("auto/retry_limit", 3).toInt();
    retryWindowMinutes_ = s.value("auto/retry_window_minutes", 10).toInt();
    retryCooldownMinutes_ = s.value("auto/retry_cooldown_minutes", 15).toInt();
    stationExpiryMinutes_ = s.value("auto/station_expiry_minutes", 3).toInt();
    maxQsoSeconds_ = s.value("auto/max_qso_seconds", 120).toInt();
    excludedPrefixes_ = s.value("auto/excluded_prefixes").toString().toUpper().split(',', Qt::SkipEmptyParts);
    for (QString &p : excludedPrefixes_) p = p.trimmed();

    hrdEnabled_ = s.value("hrdlog/enabled", false).toBool();
    hrdCall_ = s.value("hrdlog/callsign").toString().trimmed().toUpper();
    hrdCode_ = s.value("hrdlog/upload_code").toString();

    wrlEnabled_ = s.value("wrl/enabled", false).toBool();
    wrlApiKey_ = s.value("wrl/api_key").toString();
    wrlLogbookId_ = s.value("wrl/logbook_id").toString().trimmed();
}

void MshvEnhancedController::saveSettings()
{
    QSettings s(appPath_ + "/settings/mshv_enhanced.ini", QSettings::IniFormat);
    s.setValue("auto/strategy", static_cast<int>(strategy_));
    s.setValue("auto/target", static_cast<int>(target_));
    s.setValue("auto/interval", static_cast<int>(interval_));
    s.setValue("auto/qualifier", static_cast<int>(qualifier_));
    s.setValue("auto/call_non_cq", callNonCq_);
    s.setValue("auto/call_busy", callBusy_);
    s.setValue("auto/respect_directed_cq", respectDirectedCq_);
    s.setValue("auto/skip_tx1", skipTx1_);
    s.setValue("auto/fallback_cq", fallbackCq_);
    s.setValue("auto/retry_limit", retryLimit_);
    s.setValue("auto/retry_window_minutes", retryWindowMinutes_);
    s.setValue("auto/retry_cooldown_minutes", retryCooldownMinutes_);
    s.setValue("auto/station_expiry_minutes", stationExpiryMinutes_);
    s.setValue("auto/max_qso_seconds", maxQsoSeconds_);
    s.setValue("auto/excluded_prefixes", excludedPrefixes_.join(","));

    s.setValue("hrdlog/enabled", hrdEnabled_);
    s.setValue("hrdlog/callsign", hrdCall_);
    s.setValue("hrdlog/upload_code", hrdCode_);
    s.setValue("wrl/enabled", wrlEnabled_);
    s.setValue("wrl/api_key", wrlApiKey_);
    s.setValue("wrl/logbook_id", wrlLogbookId_);
    s.sync();
}

void MshvEnhancedController::openSettings()
{
    buildSettingsDialog();

    callNonCqBox_->setChecked(callNonCq_);
    callBusyBox_->setChecked(callBusy_);
    respectDirectedBox_->setChecked(respectDirectedCq_);
    skipTx1Box_->setChecked(skipTx1_);
    fallbackCqBox_->setChecked(fallbackCq_);
    retryLimitBox_->setValue(retryLimit_);
    retryWindowBox_->setValue(retryWindowMinutes_);
    retryCooldownBox_->setValue(retryCooldownMinutes_);
    stationExpiryBox_->setValue(stationExpiryMinutes_);
    maxQsoBox_->setValue(maxQsoSeconds_);
    excludedPrefixesEdit_->setText(excludedPrefixes_.join(", "));

    hrdEnabledBox_->setChecked(hrdEnabled_);
    hrdCallEdit_->setText(hrdCall_);
    hrdCodeEdit_->setText(hrdCode_);
    wrlEnabledBox_->setChecked(wrlEnabled_);
    wrlApiKeyEdit_->setText(wrlApiKey_);
    wrlLogbookEdit_->setText(wrlLogbookId_);

    if (settingsDialog_->exec() != QDialog::Accepted) return;

    callNonCq_ = callNonCqBox_->isChecked();
    callBusy_ = callBusyBox_->isChecked();
    respectDirectedCq_ = respectDirectedBox_->isChecked();
    skipTx1_ = skipTx1Box_->isChecked();
    fallbackCq_ = fallbackCqBox_->isChecked();
    retryLimit_ = retryLimitBox_->value();
    retryWindowMinutes_ = retryWindowBox_->value();
    retryCooldownMinutes_ = retryCooldownBox_->value();
    stationExpiryMinutes_ = stationExpiryBox_->value();
    maxQsoSeconds_ = maxQsoBox_->value();
    excludedPrefixes_ = excludedPrefixesEdit_->text().toUpper().split(',', Qt::SkipEmptyParts);
    for (QString &p : excludedPrefixes_) p = p.trimmed();

    hrdEnabled_ = hrdEnabledBox_->isChecked();
    hrdCall_ = upperTrimmed(hrdCallEdit_->text());
    hrdCode_ = hrdCodeEdit_->text().trimmed();
    wrlEnabled_ = wrlEnabledBox_->isChecked();
    wrlApiKey_ = wrlApiKeyEdit_->text().trimmed();
    wrlLogbookId_ = wrlLogbookEdit_->text().trimmed();

    saveSettings();
    emit skipTx1Changed(skipTx1_);
    scheduleDecision();
    updateStatus();
}

void MshvEnhancedController::toggleArm()
{
    armed_ = armButton_->isChecked();
    if (armed_) {
        emit skipTx1Changed(skipTx1_);
        emit ensureAutoRequested();
        refreshActivitySpots();
        scheduleDecision();
    } else {
        activeCall_.clear();
        activeEngaged_ = false;
        manualOverride_ = false;
    }
    updateStatus();
}

void MshvEnhancedController::haltNow()
{
    armed_ = false;
    if (armButton_) armButton_->setChecked(false);
    activeCall_.clear();
    activeEngaged_ = false;
    manualOverride_ = false;
    emit haltTxRequested();
    updateStatus();
}

void MshvEnhancedController::strategyChanged(int i)
{
    strategy_ = static_cast<Strategy>(qBound(0, i, 2));
    saveSettings();
    scheduleDecision();
    updateStatus();
}

void MshvEnhancedController::targetChanged(int i)
{
    target_ = static_cast<Target>(qBound(0, i, static_cast<int>(Icdg)));
    saveSettings();
    scheduleDecision();
    if (target_ == PotaHunter || target_ == SotaHunter || target_ == PotaSotaHunter) refreshActivitySpots();
    updateStatus();
}

void MshvEnhancedController::intervalChanged(int i)
{
    interval_ = static_cast<Interval>(qBound(0, i, static_cast<int>(Monthly)));
    saveSettings();
    scheduleDecision();
}

void MshvEnhancedController::qualifierChanged(int i)
{
    qualifier_ = static_cast<Qualifier>(qBound(0, i, static_cast<int>(PerBandUntilConfirmed)));
    saveSettings();
    scheduleDecision();
}

void MshvEnhancedController::setStationIdentity(const QString &call, const QString &grid)
{
    const QString c = upperTrimmed(call);
    const QString g = upperTrimmed(grid);
    if (c == myCall_ && g == myGrid_) return;
    myCall_ = c;
    myGrid_ = g;
    myEntity_ = resolveEntity(myCall_);
    activeCall_.clear();
    activeEngaged_ = false;
    stations_.clear();
    updateStatus();
}

void MshvEnhancedController::setBand(const QString &band)
{
    const QString normalized = normalizeBandName(band);
    if (normalized == myBand_) return;
    myBand_ = normalized;
    activeCall_.clear();
    activeEngaged_ = false;
    stations_.clear();
    scheduleDecision();
    updateStatus();
}

void MshvEnhancedController::setModeId(int modeId)
{
    const QString m = modeNameForId(modeId);
    if (m == myMode_) return;
    myMode_ = m;
    activeCall_.clear();
    activeEngaged_ = false;
    stations_.clear();
    scheduleDecision();
    updateStatus();
}

QString MshvEnhancedController::modeNameForId(int id)
{
    if (id == 11) return "FT8";
    if (id == 13) return "FT4";
    if (id == 18) return "FT2";
    return QString("MODE%1").arg(id);
}

bool MshvEnhancedController::looksLikeCall(const QString &token)
{
    static const QRegularExpression re("^(?=.{3,15}$)(?=.*[A-Z])(?=.*\\d)[A-Z0-9/]+$");
    return re.match(token.toUpper()).hasMatch();
}

bool MshvEnhancedController::looksLikeGrid(const QString &token)
{
    static const QRegularExpression re("^[A-R]{2}[0-9]{2}([A-X]{2})?$");
    return re.match(token.toUpper()).hasMatch();
}

QString MshvEnhancedController::baseCall(const QString &call)
{
    const QString full = upperTrimmed(call);
    const QStringList parts = full.split('/', Qt::SkipEmptyParts);
    QString best;
    for (const QString &p : parts) {
        const QString t = p.trimmed();
        if (t == "P" || t == "M" || t == "MM" || t == "QRP" || t == "AM") continue;
        if (!looksLikeCall(t)) continue;
        if (t.size() > best.size()) best = t;
    }
    return best.isEmpty() ? full : best;
}

QString MshvEnhancedController::normalizedCall(const QString &call)
{
    return baseCall(call);
}

void MshvEnhancedController::onDecode(QStringList decode)
{
    // Always pass the decode through to MSHV's native AutoSeq. Enhanced AUTO
    // adds target selection; it does not replace the protocol state machine.
    emit selectAutoDecode(decode);

    if (decode.size() < 5) return;
    const QString message = decode.value(4).simplified().toUpper();
    const QStringList tokens = message.split(' ', Qt::SkipEmptyParts);
    if (tokens.isEmpty()) return;

    Candidate c;
    c.rawDecode = decode;
    c.rawMessage = message;
    c.decodeTime = decode.value(0);
    c.freq = decode.value(9);
    c.band = myBand_;
    c.mode = myMode_.isEmpty() ? QStringLiteral("FT8") : myMode_;
    c.lastSeenUtc = QDateTime::currentDateTimeUtc();

    bool snrOk = false;
    c.snr = decode.value(1).toInt(&snrOk);
    if (!snrOk) c.snr = -50;

    if (tokens.value(0) == "CQ") {
        int callIndex = -1;
        for (int i = 1; i < tokens.size(); ++i) {
            if (looksLikeCall(tokens.at(i))) {
                callIndex = i;
                break;
            }
        }
        if (callIndex < 0) return;
        c.call = normalizedCall(tokens.at(callIndex));
        c.callingCq = true;
        if (callIndex > 1) c.cqModifier = tokens.at(1);
    } else if (tokens.size() >= 2 && looksLikeCall(tokens.at(0)) && looksLikeCall(tokens.at(1))) {
        const QString recipient = normalizedCall(tokens.at(0));
        const QString sender = normalizedCall(tokens.at(1));
        c.call = sender;
        c.directedToUs = (!myCall_.isEmpty() && recipient == normalizedCall(myCall_));
        c.busy = !c.directedToUs;
        // A final 73/RR73 means the station is just becoming available. This
        // makes the "call non-CQ stations" option useful without requiring
        // "call busy stations".
        const QString exchange = tokens.value(2);
        if (!c.directedToUs && (exchange == "73" || exchange == "RR73"))
            c.busy = false;
    } else {
        return;
    }

    if (c.call.isEmpty() || c.call == normalizedCall(myCall_)) return;

    for (int i = tokens.size() - 1; i >= 0; --i) {
        if (looksLikeGrid(tokens.at(i))) {
            c.grid = tokens.at(i);
            break;
        }
    }

    c.entity = resolveEntity(c.call);
    enrichCandidateFromSpots(c);
    if (!myGrid_.isEmpty() && !c.grid.isEmpty()) c.distanceKm = distanceKm(myGrid_, c.grid);

    if (stations_.contains(c.call)) {
        Candidate old = stations_.value(c.call);
        // Remember a recently heard CQ even if the station has just progressed
        // into another state; the busy flag below remains authoritative.
        if (!c.callingCq && old.callingCq && old.lastSeenUtc.secsTo(c.lastSeenUtc) < 45)
            c.callingCq = true;
        if (c.grid.isEmpty()) c.grid = old.grid;
        if (c.potaRef.isEmpty()) c.potaRef = old.potaRef;
        if (c.sotaRef.isEmpty()) c.sotaRef = old.sotaRef;
        c.pota = c.pota || old.pota;
        c.sota = c.sota || old.sota;
    }
    stations_.insert(c.call, c);

    if (!activeCall_.isEmpty() && c.call == activeCall_) {
        if (c.directedToUs) {
            activeEngaged_ = true;
            activeLastProgressUtc_ = c.lastSeenUtc;
            RetryState &rs = retries_[c.call];
            rs.attempts = 0;
            rs.bannedUntilUtc = QDateTime();
        } else if (c.busy && !activeEngaged_ && !manualOverride_) {
            clearActive("target started a QSO with another station", false);
        }
    }

    if (armed_ && c.directedToUs && strategy_ != Hunt) {
        if (activeCall_.isEmpty() || (!activeEngaged_ && activeCall_ != c.call)) {
            if (!activeCall_.isEmpty() && activeCall_ != c.call) emit haltTxRequested();
            activeCall_ = c.call;
            activeEngaged_ = true;
            manualOverride_ = false;
            activeStartedUtc_ = c.lastSeenUtc;
            activeLastProgressUtc_ = c.lastSeenUtc;
            activeProgress_ = 1;
            emit ensureAutoRequested();
        }
    }

    pruneStations();
    scheduleDecision();
    updateStatus();
}

void MshvEnhancedController::onManualTarget(QString, QString selectedCall, QString, QString, QString)
{
    const QString call = normalizedCall(selectedCall);
    if (call.isEmpty()) return;
    RetryState &rs = retries_[call];
    rs.attempts = 0;
    rs.windowStartUtc = QDateTime();
    rs.bannedUntilUtc = QDateTime();

    activeCall_ = call;
    activeEngaged_ = false;
    manualOverride_ = true;
    activeStartedUtc_ = QDateTime::currentDateTimeUtc();
    activeLastProgressUtc_ = activeStartedUtc_;
    activeProgress_ = 0;
    updateStatus();
}

void MshvEnhancedController::onQsoProgress(int progress)
{
    activeProgress_ = progress;
    if (!activeCall_.isEmpty() && progress > 0) {
        activeLastProgressUtc_ = QDateTime::currentDateTimeUtc();
        if (progress >= 2) activeEngaged_ = true;
    }
    updateStatus();
}

void MshvEnhancedController::onLoggedQso(QStringList)
{
    // Kept for compatibility with derivative builds that expose the old signal.
}

void MshvEnhancedController::onAdifRecord(QString adif)
{
    const QString call = normalizedCall(adifValue(adif, "CALL"));

    HistoryRow row;
    row.call = call;
    row.band = normalizeBandName(adifValue(adif, "BAND"));
    row.mode = adifValue(adif, "SUBMODE");
    if (row.mode.isEmpty()) row.mode = adifValue(adif, "MODE");
    row.grid = adifValue(adif, "GRIDSQUARE").toUpper();
    row.country = adifValue(adif, "COUNTRY");
    row.cqZone = adifValue(adif, "CQZ").toInt();
    row.ituZone = adifValue(adif, "ITUZ").toInt();
    row.whenUtc = adifTime(adif);
    row.confirmed = truthyAdif(adifValue(adif, "QSL_RCVD")) ||
                    truthyAdif(adifValue(adif, "LOTW_QSL_RCVD")) ||
                    truthyAdif(adifValue(adif, "EQSL_QSL_RCVD")) ||
                    truthyAdif(adifValue(adif, "APP_QRZLOG_STATUS")) ||
                    truthyAdif(adifValue(adif, "QRZCOM_QSO_DOWNLOAD_STATUS"));
    history_.push_back(row);

    if (!call.isEmpty()) {
        RetryState &rs = retries_[call];
        rs.attempts = 0;
        rs.windowStartUtc = QDateTime();
        rs.bannedUntilUtc = QDateTime();
    }

    if (!activeCall_.isEmpty() && (call.isEmpty() || call == activeCall_)) {
        activeCall_.clear();
        activeEngaged_ = false;
        manualOverride_ = false;
        activeProgress_ = 0;
        emit ensureAutoRequested();
        scheduleDecision();
    }

    if (hrdEnabled_) enqueueHrdLog(adif);
    if (wrlEnabled_) enqueueWrl(adif);
    pumpUploads();
    updateStatus();
}

void MshvEnhancedController::scheduleDecision()
{
    if (!armed_ || strategy_ == Answer || !activeCall_.isEmpty()) return;
    decisionTimer_.start();
}

void MshvEnhancedController::decideNow()
{
    if (!armed_ || strategy_ == Answer || !activeCall_.isEmpty()) return;

    if (target_ == CallCq) {
        if (fallbackCq_) {
            emit requestCq();
            emit ensureAutoRequested();
        }
        return;
    }

    const QVector<Candidate> candidates = rankedCandidates();
    if (!candidates.isEmpty()) {
        selectCandidate(candidates.first());
    } else if (fallbackCq_) {
        emit requestCq();
        emit ensureAutoRequested();
    }
    updateStatus();
}

void MshvEnhancedController::selectCandidate(const Candidate &candidate)
{
    if (!eligible(candidate)) return;

    activeCall_ = candidate.call;
    activeEngaged_ = false;
    manualOverride_ = false;
    activeStartedUtc_ = QDateTime::currentDateTimeUtc();
    activeLastProgressUtc_ = activeStartedUtc_;
    activeProgress_ = 0;
    noteAttempt(candidate.call);

    emit ensureAutoRequested();
    emit selectHuntDecode(candidate.rawMessage,
                          candidate.call,
                          candidate.decodeTime,
                          QString::number(candidate.snr),
                          candidate.freq);
    updateStatus();
}

void MshvEnhancedController::watchdogTick()
{
    pruneStations();

    if (!armed_ || activeCall_.isEmpty()) return;

    const QDateTime now = QDateTime::currentDateTimeUtc();
    if (!activeStartedUtc_.isValid()) activeStartedUtc_ = now;
    if (!activeLastProgressUtc_.isValid()) activeLastProgressUtc_ = activeStartedUtc_;

    const int attemptSeconds = qMax(15, maxQsoSeconds_ / qMax(1, retryLimit_));

    if (manualOverride_) {
        if (activeLastProgressUtc_.secsTo(now) > maxQsoSeconds_) {
            clearActive("manual target watchdog", false);
        }
        return;
    }

    if (!activeEngaged_) {
        if (activeStartedUtc_.secsTo(now) < attemptSeconds) return;

        RetryState &rs = retries_[activeCall_];
        if (rs.attempts >= retryLimit_) {
            rs.bannedUntilUtc = now.addSecs(retryCooldownMinutes_ * 60);
            clearActive("retry limit reached", true);
        } else {
            clearActive("retrying unanswered target", false);
        }
        return;
    }

    if (activeLastProgressUtc_.secsTo(now) > maxQsoSeconds_) {
        RetryState &rs = retries_[activeCall_];
        rs.bannedUntilUtc = now.addSecs(retryCooldownMinutes_ * 60);
        clearActive("stalled QSO watchdog", true);
    }
}

void MshvEnhancedController::clearActive(const QString &reason, bool cooldown)
{
    Q_UNUSED(reason);
    const QString old = activeCall_;
    if (cooldown && !old.isEmpty()) {
        RetryState &rs = retries_[old];
        rs.bannedUntilUtc = QDateTime::currentDateTimeUtc().addSecs(retryCooldownMinutes_ * 60);
    }

    if (!old.isEmpty()) emit haltTxRequested();
    activeCall_.clear();
    activeEngaged_ = false;
    manualOverride_ = false;
    activeProgress_ = 0;
    emit ensureAutoRequested();
    scheduleDecision();
    updateStatus();
}

void MshvEnhancedController::noteAttempt(const QString &call)
{
    const QDateTime now = QDateTime::currentDateTimeUtc();
    RetryState &rs = retries_[call];
    if (!rs.windowStartUtc.isValid() || rs.windowStartUtc.secsTo(now) > retryWindowMinutes_ * 60) {
        rs.attempts = 0;
        rs.windowStartUtc = now;
    }
    ++rs.attempts;
}

bool MshvEnhancedController::retryBanned(const QString &call) const
{
    if (!retries_.contains(call)) return false;
    const RetryState rs = retries_.value(call);
    return rs.bannedUntilUtc.isValid() && rs.bannedUntilUtc > QDateTime::currentDateTimeUtc();
}

bool MshvEnhancedController::excluded(const QString &call) const
{
    const QString c = call.toUpper();
    for (const QString &p : excludedPrefixes_) {
        if (!p.isEmpty() && c.startsWith(p)) return true;
    }
    return false;
}

bool MshvEnhancedController::directedCqTargetsUs(const Candidate &candidate) const
{
    if (!respectDirectedCq_ || candidate.cqModifier.isEmpty()) return true;

    const QString m = candidate.cqModifier.toUpper();
    if (m == "POTA" || m == "SOTA" || m == "TEST" || m == "CONTEST") return true;

    if (m == "DX") {
        if (!myEntity_.valid || !candidate.entity.valid) return true;
        return myEntity_.continent != candidate.entity.continent;
    }

    static const QSet<QString> continents = QSet<QString>()
        << "AF" << "AN" << "AS" << "EU" << "NA" << "OC" << "SA";
    if (continents.contains(m)) {
        return myEntity_.valid && myEntity_.continent == m;
    }

    if (!myCall_.isEmpty() && normalizedCall(myCall_).startsWith(m)) return true;
    if (myEntity_.valid && myEntity_.prefix.startsWith(m)) return true;

    return false;
}

bool MshvEnhancedController::eligible(const Candidate &candidate) const
{
    if (candidate.call.isEmpty()) return false;
    if (excluded(candidate.call)) return false;
    if (retryBanned(candidate.call)) return false;
    if (candidate.lastSeenUtc.secsTo(QDateTime::currentDateTimeUtc()) > stationExpiryMinutes_ * 60) return false;
    if (!candidate.directedToUs) {
        if (!candidate.callingCq && !callNonCq_) return false;
        if (candidate.busy && !callBusy_) return false;
        if (candidate.callingCq && !directedCqTargetsUs(candidate)) return false;
    }
    if (!targetNeeded(candidate)) return false;
    if (historyBlocks(candidate)) return false;
    return true;
}

QVector<MshvEnhancedController::Candidate> MshvEnhancedController::rankedCandidates() const
{
    QVector<Candidate> out;
    for (auto it = stations_.constBegin(); it != stations_.constEnd(); ++it) {
        if (eligible(it.value())) out.push_back(it.value());
    }

    std::stable_sort(out.begin(), out.end(), [this](const Candidate &a, const Candidate &b) {
        const qint64 sa = score(a);
        const qint64 sb = score(b);
        if (sa != sb) return sa > sb;
        if (a.snr != b.snr) return a.snr > b.snr;
        return a.call < b.call;
    });
    return out;
}

qint64 MshvEnhancedController::score(const Candidate &candidate) const
{
    qint64 s = 0;
    if (candidate.directedToUs) s += 1000000000LL;

    const int level = targetNeedLevel(candidate);
    s += static_cast<qint64>(level) * 10000000LL;

    if (target_ == PotaSotaHunter) {
        if (candidate.pota || candidate.sota) s += 8000000LL;
    } else if (target_ == PotaHunter && candidate.pota) {
        s += 8000000LL;
    } else if (target_ == SotaHunter && candidate.sota) {
        s += 8000000LL;
    }

    if (target_ == Far && candidate.distanceKm >= 0.0)
        s += static_cast<qint64>(candidate.distanceKm * 100.0);
    else if (target_ == Nearby && candidate.distanceKm >= 0.0)
        s += qMax<qint64>(0, 2000000LL - static_cast<qint64>(candidate.distanceKm * 100.0));
    else if (target_ == Strongest)
        s += static_cast<qint64>(candidate.snr + 60) * 10000LL;

    // General tie-breakers: new achievements, then SNR.
    if (candidate.entity.valid && !achievementConfirmed(candidate, false)) s += 500000;
    if (!candidate.grid.isEmpty()) {
        bool seenGrid = false;
        for (const HistoryRow &h : history_) if (h.grid == candidate.grid) { seenGrid = true; break; }
        if (!seenGrid) s += 150000;
    }
    s += static_cast<qint64>(candidate.snr + 60) * 1000LL;
    if (candidate.busy) s -= 100000;
    return s;
}

int MshvEnhancedController::targetNeedLevel(const Candidate &candidate) const
{
    const bool bandSpecific = qualifier_ == DifferentBands || qualifier_ == PerBandUntilConfirmed;

    auto workedEntity = [this, &candidate, bandSpecific]() {
        if (!candidate.entity.valid) return true;
        for (const HistoryRow &h : history_) {
            if (bandSpecific && !candidate.band.isEmpty() &&
            normalizeBandName(h.band) != normalizeBandName(candidate.band)) continue;
            if (!h.country.isEmpty() && h.country.compare(candidate.entity.country, Qt::CaseInsensitive) == 0) return true;
            Entity e = resolveEntity(h.call);
            if (e.valid && e.country == candidate.entity.country) return true;
        }
        return false;
    };

    auto workedGrid = [this, &candidate, bandSpecific]() {
        if (candidate.grid.isEmpty()) return true;
        for (const HistoryRow &h : history_) {
            if (bandSpecific && !candidate.band.isEmpty() &&
            normalizeBandName(h.band) != normalizeBandName(candidate.band)) continue;
            if (h.grid.toUpper() == candidate.grid.toUpper()) return true;
        }
        return false;
    };

    auto workedItu = [this, &candidate, bandSpecific]() {
        if (candidate.entity.ituZone <= 0) return true;
        for (const HistoryRow &h : history_) {
            if (bandSpecific && !candidate.band.isEmpty() &&
            normalizeBandName(h.band) != normalizeBandName(candidate.band)) continue;
            int z = h.ituZone;
            if (z <= 0) z = resolveEntity(h.call).ituZone;
            if (z == candidate.entity.ituZone) return true;
        }
        return false;
    };

    auto workedCq = [this, &candidate, bandSpecific]() {
        if (candidate.entity.cqZone <= 0) return true;
        for (const HistoryRow &h : history_) {
            if (bandSpecific && !candidate.band.isEmpty() &&
            normalizeBandName(h.band) != normalizeBandName(candidate.band)) continue;
            int z = h.cqZone;
            if (z <= 0) z = resolveEntity(h.call).cqZone;
            if (z == candidate.entity.cqZone) return true;
        }
        return false;
    };

    if (target_ == Dxcc) return workedEntity() ? 0 : 1;
    if (target_ == Grid) return workedGrid() ? 0 : 1;
    if (target_ == ItuZone) return workedItu() ? 0 : 1;
    if (target_ == CqZone) return workedCq() ? 0 : 1;
    if (target_ == Icdg) {
        if (!workedItu()) return 4;
        if (!workedCq()) return 3;
        if (!workedEntity()) return 2;
        if (!workedGrid()) return 1;
        return 0;
    }
    return 1;
}

bool MshvEnhancedController::targetNeeded(const Candidate &candidate) const
{
    if (target_ == CallCq) return false;
    if (target_ == PotaHunter) return candidate.pota;
    if (target_ == SotaHunter) return candidate.sota;
    if (target_ == PotaSotaHunter) return candidate.pota || candidate.sota;
    if (target_ == Dxcc || target_ == Grid || target_ == ItuZone || target_ == CqZone || target_ == Icdg)
        return targetNeedLevel(candidate) > 0;
    return true;
}

bool MshvEnhancedController::historyMatchesPeriod(const HistoryRow &row, const Candidate &candidate, bool bandSpecific) const
{
    if (normalizedCall(row.call) != normalizedCall(candidate.call)) return false;
    if (bandSpecific && !candidate.band.isEmpty() &&
        normalizeBandName(row.band) != normalizeBandName(candidate.band)) return false;
    if (interval_ == Always) return false;
    if (interval_ == Once) return true;

    const QDateTime now = QDateTime::currentDateTimeUtc();
    if (!row.whenUtc.isValid()) return interval_ == Once;

    if (interval_ == Daily) return row.whenUtc.date() == now.date();
    if (interval_ == Weekly) return row.whenUtc.daysTo(now) >= 0 && row.whenUtc.daysTo(now) < 7;
    if (interval_ == Monthly) {
        return row.whenUtc.date().year() == now.date().year() &&
               row.whenUtc.date().month() == now.date().month();
    }
    return false;
}

bool MshvEnhancedController::achievementConfirmed(const Candidate &candidate, bool bandSpecific) const
{
    for (const HistoryRow &h : history_) {
        if (!h.confirmed) continue;
        if (bandSpecific && !candidate.band.isEmpty() &&
            normalizeBandName(h.band) != normalizeBandName(candidate.band)) continue;

        if (target_ == Dxcc || target_ == Icdg) {
            Entity e = resolveEntity(h.call);
            if (candidate.entity.valid && ((e.valid && e.country == candidate.entity.country) ||
                (!h.country.isEmpty() && h.country.compare(candidate.entity.country, Qt::CaseInsensitive) == 0)))
                return true;
        }
        if ((target_ == Grid || target_ == Icdg) && !candidate.grid.isEmpty() && h.grid.toUpper() == candidate.grid.toUpper())
            return true;
        if ((target_ == ItuZone || target_ == Icdg) && candidate.entity.ituZone > 0) {
            int z = h.ituZone > 0 ? h.ituZone : resolveEntity(h.call).ituZone;
            if (z == candidate.entity.ituZone) return true;
        }
        if ((target_ == CqZone || target_ == Icdg) && candidate.entity.cqZone > 0) {
            int z = h.cqZone > 0 ? h.cqZone : resolveEntity(h.call).cqZone;
            if (z == candidate.entity.cqZone) return true;
        }
        if ((target_ == Anyone || target_ == Nearby || target_ == Far || target_ == Strongest ||
             target_ == PotaHunter || target_ == SotaHunter || target_ == PotaSotaHunter) &&
            normalizedCall(h.call) == normalizedCall(candidate.call))
            return true;
    }
    return false;
}

bool MshvEnhancedController::historyBlocks(const Candidate &candidate) const
{
    const bool bandSpecific = qualifier_ == DifferentBands || qualifier_ == PerBandUntilConfirmed;

    if ((qualifier_ == UntilConfirmed || qualifier_ == PerBandUntilConfirmed) &&
        achievementConfirmed(candidate, bandSpecific))
        return true;

    for (const HistoryRow &h : history_) {
        if (historyMatchesPeriod(h, candidate, bandSpecific)) return true;
    }
    return false;
}

void MshvEnhancedController::pruneStations()
{
    const QDateTime now = QDateTime::currentDateTimeUtc();
    QList<QString> remove;
    for (auto it = stations_.constBegin(); it != stations_.constEnd(); ++it) {
        if (it.value().lastSeenUtc.secsTo(now) > stationExpiryMinutes_ * 60)
            remove << it.key();
    }
    for (const QString &k : remove) stations_.remove(k);
}

void MshvEnhancedController::updateStatus()
{
    if (!stateLabel_) return;
    if (!armed_) {
        stateLabel_->setText(tr("DISARMED"));
        stateLabel_->setStyleSheet(QString());
    } else if (!activeCall_.isEmpty()) {
        stateLabel_->setText(activeEngaged_ ? tr("LOCKED") : tr("CALLING"));
        stateLabel_->setStyleSheet("QLabel{font-weight:bold;}");
    } else {
        stateLabel_->setText(tr("ARMED"));
        stateLabel_->setStyleSheet("QLabel{font-weight:bold;}");
    }

    if (activeLabel_) {
        QString t = activeCall_.isEmpty() ? tr("No active QSO") : tr("Target: ") + activeCall_;
        if (!activeCall_.isEmpty()) t += QString(" [%1]").arg(activeProgress_);
        t += QString(" | %1 %2").arg(stations_.size()).arg(tr("stations"));
        activeLabel_->setText(t);
    }

    if (armButton_) {
        armButton_->setText(armed_ ? tr("DISARM") : tr("ARM"));
        if (armed_) armButton_->setStyleSheet("QPushButton{background-color:#8b1e1e;color:white;font-weight:bold;}");
        else armButton_->setStyleSheet(QString());
    }
}

QString MshvEnhancedController::adifValue(const QString &adif, const QString &field)
{
    const QString escaped = QRegularExpression::escape(field);
    QRegularExpression re(QString("<\\s*%1\\s*:\\s*\\d+(?::[^>]*)?\\s*>([^<]*)").arg(escaped),
                          QRegularExpression::CaseInsensitiveOption);
    QRegularExpressionMatch m = re.match(adif);
    return m.hasMatch() ? m.captured(1).trimmed() : QString();
}

QDateTime MshvEnhancedController::adifTime(const QString &adif)
{
    const QString d = adifValue(adif, "QSO_DATE");
    QString t = adifValue(adif, "TIME_ON");
    if (d.size() != 8) return QDateTime();
    while (t.size() < 6) t.append('0');
    const QDate date = QDate::fromString(d, "yyyyMMdd");
    const QTime time = QTime::fromString(t.left(6), "hhmmss");
    if (!date.isValid() || !time.isValid()) return QDateTime();
    return QDateTime(date, time, Qt::UTC);
}

void MshvEnhancedController::loadHistory()
{
    history_.clear();
    QFile f(appPath_ + "/log/mshvlog.adi");
    if (!f.open(QIODevice::ReadOnly | QIODevice::Text)) return;
    const QString all = QString::fromUtf8(f.readAll());
    const QStringList records = all.split(QRegularExpression("<\\s*EOR\\s*>", QRegularExpression::CaseInsensitiveOption),
                                          Qt::SkipEmptyParts);
    history_.reserve(records.size());

    for (const QString &adif : records) {
        HistoryRow row;
        row.call = normalizedCall(adifValue(adif, "CALL"));
        if (row.call.isEmpty()) continue;
        row.band = normalizeBandName(adifValue(adif, "BAND"));
        row.mode = adifValue(adif, "SUBMODE");
        if (row.mode.isEmpty()) row.mode = adifValue(adif, "MODE");
        row.grid = adifValue(adif, "GRIDSQUARE").toUpper();
        row.country = adifValue(adif, "COUNTRY");
        row.cqZone = adifValue(adif, "CQZ").toInt();
        row.ituZone = adifValue(adif, "ITUZ").toInt();
        row.whenUtc = adifTime(adif);
        row.confirmed = truthyAdif(adifValue(adif, "QSL_RCVD")) ||
                        truthyAdif(adifValue(adif, "LOTW_QSL_RCVD")) ||
                        truthyAdif(adifValue(adif, "EQSL_QSL_RCVD")) ||
                        truthyAdif(adifValue(adif, "APP_QRZLOG_STATUS")) ||
                        truthyAdif(adifValue(adif, "QRZCOM_QSO_DOWNLOAD_STATUS"));
        history_.push_back(row);
    }
}

void MshvEnhancedController::loadCty()
{
    cty_.clear();
    QFile f(QCoreApplication::applicationDirPath() + "/settings/database/cty.dat");
    if (!f.open(QIODevice::ReadOnly | QIODevice::Text)) return;

    QString logical;
    while (!f.atEnd()) {
        QString line = QString::fromUtf8(f.readLine());
        line.remove('\r');
        line.remove('\n');
        logical += line;
        if (!logical.endsWith(';')) continue;
        logical.chop(1);

        const QStringList fields = logical.split(':');
        logical.clear();
        if (fields.size() < 8) continue;

        Entity base;
        base.valid = true;
        base.country = fields.value(0).trimmed();
        base.cqZone = fields.value(1).trimmed().toInt();
        base.ituZone = fields.value(2).trimmed().toInt();
        base.continent = fields.value(3).trimmed().toUpper();

        QString primary = fields.value(7).trimmed().toUpper();
        primary.remove('*');
        if (!primary.isEmpty()) {
            CtyRecord r;
            r.key = primary;
            r.entity = base;
            r.entity.prefix = primary;
            cty_.push_back(r);
        }

        if (fields.size() < 9) continue;
        const QStringList aliases = fields.value(8).split(',', Qt::SkipEmptyParts);
        for (QString token : aliases) {
            token = token.trimmed().toUpper();
            if (token.isEmpty()) continue;
            CtyRecord r;
            r.entity = base;
            if (token.startsWith('=')) {
                r.exact = true;
                token.remove(0, 1);
            }

            QRegularExpression cqRe("\\((\\d+)\\)");
            QRegularExpressionMatch cqM = cqRe.match(token);
            if (cqM.hasMatch()) {
                r.entity.cqZone = cqM.captured(1).toInt();
                token.remove(cqM.capturedStart(), cqM.capturedLength());
            }
            QRegularExpression ituRe("\\[(\\d+)\\]");
            QRegularExpressionMatch ituM = ituRe.match(token);
            if (ituM.hasMatch()) {
                r.entity.ituZone = ituM.captured(1).toInt();
                token.remove(ituM.capturedStart(), ituM.capturedLength());
            }
            QRegularExpression contRe("\\{([A-Z]{2})\\}");
            QRegularExpressionMatch contM = contRe.match(token);
            if (contM.hasMatch()) {
                r.entity.continent = contM.captured(1);
                token.remove(contM.capturedStart(), contM.capturedLength());
            }
            token.remove(QRegularExpression("<[^>]*>"));
            token.remove(QRegularExpression("~[^~]*~"));
            token = token.trimmed();
            if (token.isEmpty()) continue;
            r.key = token;
            r.entity.prefix = token;
            cty_.push_back(r);
        }
    }

    std::stable_sort(cty_.begin(), cty_.end(), [](const CtyRecord &a, const CtyRecord &b) {
        if (a.exact != b.exact) return a.exact > b.exact;
        if (a.key.size() != b.key.size()) return a.key.size() > b.key.size();
        return a.key < b.key;
    });
}

MshvEnhancedController::Entity MshvEnhancedController::resolveEntity(const QString &call) const
{
    const QString full = upperTrimmed(call);
    QStringList forms;
    forms << full;
    const QString bc = baseCall(full);
    if (!forms.contains(bc)) forms << bc;
    const QStringList parts = full.split('/', Qt::SkipEmptyParts);
    for (const QString &p : parts) {
        const QString u = p.toUpper();
        if (u != "P" && u != "M" && u != "MM" && u != "QRP" && u != "AM" && !forms.contains(u))
            forms << u;
    }

    for (const QString &form : forms) {
        for (const CtyRecord &r : cty_) {
            if ((r.exact && form == r.key) || (!r.exact && form.startsWith(r.key)))
                return r.entity;
        }
    }
    return Entity();
}

bool MshvEnhancedController::gridToLatLon(const QString &gridInput, double &lat, double &lon)
{
    QString g = gridInput.trimmed().toUpper();
    if (g.size() < 4) return false;
    if (!looksLikeGrid(g.left(qMin(6, g.size())))) return false;

    const int a = g.at(0).unicode() - 'A';
    const int b = g.at(1).unicode() - 'A';
    const int c = g.at(2).digitValue();
    const int d = g.at(3).digitValue();
    if (a < 0 || a > 17 || b < 0 || b > 17 || c < 0 || d < 0) return false;

    lon = -180.0 + a * 20.0 + c * 2.0;
    lat = -90.0 + b * 10.0 + d * 1.0;

    double lonCell = 2.0;
    double latCell = 1.0;
    if (g.size() >= 6) {
        const int e = g.at(4).unicode() - 'A';
        const int f = g.at(5).unicode() - 'A';
        if (e >= 0 && e < 24 && f >= 0 && f < 24) {
            lon += e * (2.0 / 24.0);
            lat += f * (1.0 / 24.0);
            lonCell = 2.0 / 24.0;
            latCell = 1.0 / 24.0;
        }
    }
    lon += lonCell / 2.0;
    lat += latCell / 2.0;
    return true;
}

double MshvEnhancedController::distanceKm(const QString &a, const QString &b)
{
    double lat1 = 0.0, lon1 = 0.0, lat2 = 0.0, lon2 = 0.0;
    if (!gridToLatLon(a, lat1, lon1) || !gridToLatLon(b, lat2, lon2)) return -1.0;
    const double pi = 3.14159265358979323846;
    const double p1 = lat1 * pi / 180.0;
    const double p2 = lat2 * pi / 180.0;
    const double dp = (lat2 - lat1) * pi / 180.0;
    const double dl = (lon2 - lon1) * pi / 180.0;
    const double h = std::sin(dp/2.0) * std::sin(dp/2.0) +
                     std::cos(p1) * std::cos(p2) * std::sin(dl/2.0) * std::sin(dl/2.0);
    return 6371.0088 * 2.0 * std::atan2(std::sqrt(h), std::sqrt(1.0 - h));
}

void MshvEnhancedController::refreshActivitySpots()
{
    if (target_ != PotaHunter && target_ != SotaHunter && target_ != PotaSotaHunter) return;

    if (target_ == PotaHunter || target_ == PotaSotaHunter) {
        QNetworkRequest req(QUrl("https://api.pota.app/spot/activator"));
        req.setRawHeader("User-Agent", "MSHV-Enhanced/0.1.0");
        QNetworkReply *reply = network_.get(req);
        reply->setProperty("purpose", "pota");
    }
    if (target_ == SotaHunter || target_ == PotaSotaHunter) {
        QNetworkRequest req(QUrl("https://api2.sota.org.uk/api/spots/-1/all"));
        req.setRawHeader("User-Agent", "MSHV-Enhanced/0.1.0");
        QNetworkReply *reply = network_.get(req);
        reply->setProperty("purpose", "sota");
    }
}

void MshvEnhancedController::parsePotaReply(const QByteArray &data)
{
    QJsonParseError err;
    const QJsonDocument doc = QJsonDocument::fromJson(data, &err);
    if (err.error != QJsonParseError::NoError || !doc.isArray()) return;

    QHash<QString,QString> next;
    for (const QJsonValue &v : doc.array()) {
        const QJsonObject o = v.toObject();
        const QString call = normalizedCall(jsonString(o, "activator", "activatorCallsign", "callsign"));
        const QString ref = jsonString(o, "reference", "parkReference", "park");
        if (!call.isEmpty() && !ref.isEmpty()) next.insert(call, ref);
    }
    potaRefs_ = next;
    for (auto it = stations_.begin(); it != stations_.end(); ++it) enrichCandidateFromSpots(it.value());
    scheduleDecision();
}

void MshvEnhancedController::parseSotaReply(const QByteArray &data)
{
    QJsonParseError err;
    const QJsonDocument doc = QJsonDocument::fromJson(data, &err);
    if (err.error != QJsonParseError::NoError || !doc.isArray()) return;

    QHash<QString,QString> next;
    for (const QJsonValue &v : doc.array()) {
        const QJsonObject o = v.toObject();
        const QString call = normalizedCall(jsonString(o, "activatorCallsign", "activator", "callsign"));
        QString ref = jsonString(o, "summitCode", "summitRef", "reference");
        const QString assoc = jsonString(o, "associationCode");
        if (!assoc.isEmpty() && !ref.isEmpty() && !ref.contains('/')) ref = assoc + "/" + ref;
        if (!call.isEmpty() && !ref.isEmpty()) next.insert(call, ref);
    }
    sotaRefs_ = next;
    for (auto it = stations_.begin(); it != stations_.end(); ++it) enrichCandidateFromSpots(it.value());
    scheduleDecision();
}

void MshvEnhancedController::enrichCandidateFromSpots(Candidate &candidate) const
{
    if (potaRefs_.contains(candidate.call)) {
        candidate.pota = true;
        candidate.potaRef = potaRefs_.value(candidate.call);
    }
    if (sotaRefs_.contains(candidate.call)) {
        candidate.sota = true;
        candidate.sotaRef = sotaRefs_.value(candidate.call);
    }
    if (candidate.rawMessage.contains(" POTA")) candidate.pota = true;
    if (candidate.rawMessage.contains(" SOTA")) candidate.sota = true;
}

void MshvEnhancedController::networkFinished(QNetworkReply *reply)
{
    const QString purpose = reply->property("purpose").toString();
    const QByteArray data = reply->readAll();

    if (purpose == "pota") {
        if (reply->error() == QNetworkReply::NoError) parsePotaReply(data);
        reply->deleteLater();
        return;
    }
    if (purpose == "sota") {
        if (reply->error() == QNetworkReply::NoError) parseSotaReply(data);
        reply->deleteLater();
        return;
    }

    if (purpose == "upload") {
        completeUpload(reply);
        reply->deleteLater();
        return;
    }

    reply->deleteLater();
}

void MshvEnhancedController::enqueueHrdLog(const QString &adif)
{
    if (hrdCall_.isEmpty() || hrdCode_.isEmpty()) return;

    QUrlQuery form;
    form.addQueryItem("Callsign", hrdCall_);
    form.addQueryItem("Code", hrdCode_);
    form.addQueryItem("APP", "MSHV Enhanced 0.1.0");
    form.addQueryItem("CMD", "INSERT");
    form.addQueryItem("ADIFDATA", adif);

    UploadJob j;
    j.service = "hrdlog";
    j.url = QUrl("https://robot.hrdlog.net/NewEntry.aspx");
    j.body = form.query(QUrl::FullyEncoded).toUtf8();
    j.headers.insert("Content-Type", "application/x-www-form-urlencoded");
    uploadQueue_.push_back(j);
}

QJsonObject MshvEnhancedController::wrlJsonFromAdif(const QString &adif) const
{
    QJsonObject o;
    o.insert("programId", "MSHV Enhanced");
    const QString call = adifValue(adif, "CALL");
    const QString band = adifValue(adif, "BAND");
    QString mode = adifValue(adif, "SUBMODE");
    if (mode.isEmpty()) mode = adifValue(adif, "MODE");
    const QString freq = adifValue(adif, "FREQ");
    const QString rstS = adifValue(adif, "RST_SENT");
    const QString rstR = adifValue(adif, "RST_RCVD");
    const QString grid = adifValue(adif, "GRIDSQUARE");
    const QString myGrid = adifValue(adif, "MY_GRIDSQUARE");
    const QString state = adifValue(adif, "STATE");
    const QString notes = adifValue(adif, "COMMENT");
    const QString station = adifValue(adif, "STATION_CALLSIGN");
    const QString pwr = adifValue(adif, "TX_PWR");

    o.insert("call", call);
    const QDateTime dt = adifTime(adif);
    if (dt.isValid()) o.insert("timestamp", dt.toString(Qt::ISODate));
    if (!freq.isEmpty()) o.insert("freq", freq.toDouble());
    if (!band.isEmpty()) o.insert("band", band);
    if (!mode.isEmpty()) o.insert("mode", mode);
    if (!rstS.isEmpty()) o.insert("rstSent", rstS);
    if (!rstR.isEmpty()) o.insert("rstRcvd", rstR);
    if (!pwr.isEmpty()) o.insert("txPwr", pwr.toDouble());
    if (!station.isEmpty()) o.insert("stationCallsign", station);
    if (!grid.isEmpty()) o.insert("gridsquare", grid);
    if (!myGrid.isEmpty()) o.insert("myGridsquare", myGrid);
    if (!state.isEmpty()) o.insert("state", state);
    if (!notes.isEmpty()) o.insert("notes", notes);
    if (!wrlLogbookId_.isEmpty()) o.insert("logbookId", wrlLogbookId_);

    const QString pota = adifValue(adif, "POTA_REF");
    const QString sota = adifValue(adif, "SOTA_REF");
    if (!pota.isEmpty() || !sota.isEmpty()) {
        QJsonArray acts;
        if (!pota.isEmpty()) {
            QJsonObject a; a.insert("type", "POTA"); a.insert("ref", pota); a.insert("isPrimary", true); acts.append(a);
        }
        if (!sota.isEmpty()) {
            QJsonObject a; a.insert("type", "SOTA"); a.insert("ref", sota); if (acts.isEmpty()) a.insert("isPrimary", true); acts.append(a);
        }
        o.insert("theirActivities", acts);
    }
    return o;
}

void MshvEnhancedController::enqueueWrl(const QString &adif)
{
    if (wrlApiKey_.isEmpty()) return;

    UploadJob j;
    j.service = "wrl";
    j.url = QUrl("https://api.worldradioleague.com/v1/contacts");
    j.body = QJsonDocument(wrlJsonFromAdif(adif)).toJson(QJsonDocument::Compact);
    j.headers.insert("Content-Type", "application/json");
    j.headers.insert("Authorization", QByteArray("Bearer ") + wrlApiKey_.toUtf8());
    uploadQueue_.push_back(j);
}

void MshvEnhancedController::pumpUploads()
{
    if (uploadBusy_ || uploadQueue_.isEmpty()) return;

    UploadJob j = uploadQueue_.first();
    uploadQueue_.remove(0);
    QNetworkRequest req(j.url);
    for (auto it = j.headers.constBegin(); it != j.headers.constEnd(); ++it)
        req.setRawHeader(it.key(), it.value());
    req.setRawHeader("User-Agent", "MSHV-Enhanced/0.1.0");

    QNetworkReply *reply = network_.post(req, j.body);
    reply->setProperty("purpose", "upload");
    reply->setProperty("upload_service", j.service);
    reply->setProperty("upload_body", j.body);
    reply->setProperty("upload_attempts", j.attempts);
    uploadBusy_ = true;
}

void MshvEnhancedController::completeUpload(QNetworkReply *reply)
{
    uploadBusy_ = false;
    const int status = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
    const bool ok = reply->error() == QNetworkReply::NoError && status >= 200 && status < 300;

    int retryDelayMs = 250;
    if (!ok) {
        const QString service = reply->property("upload_service").toString();
        const int attempts = reply->property("upload_attempts").toInt();

        // Authentication and validation errors require operator action; do not
        // hammer either service. Retry only network/5xx/429 failures.
        const bool transient =
            reply->error() != QNetworkReply::NoError ||
            status == 429 ||
            status >= 500;

        if (transient && attempts < 2) {
            UploadJob j;
            j.service = service;
            j.attempts = attempts + 1;
            j.body = reply->property("upload_body").toByteArray();
            if (service == "hrdlog") {
                j.url = QUrl("https://robot.hrdlog.net/NewEntry.aspx");
                j.headers.insert("Content-Type", "application/x-www-form-urlencoded");
            } else if (service == "wrl") {
                j.url = QUrl("https://api.worldradioleague.com/v1/contacts");
                j.headers.insert("Content-Type", "application/json");
                j.headers.insert("Authorization", QByteArray("Bearer ") + wrlApiKey_.toUtf8());
            }
            uploadQueue_.push_back(j);

            if (status == 429) {
                bool retryOk = false;
                const int retrySeconds = reply->rawHeader("Retry-After").toInt(&retryOk);
                if (retryOk && retrySeconds > 0)
                    retryDelayMs = qMin(retrySeconds, 300) * 1000;
            } else {
                retryDelayMs = 1500 * (attempts + 1);
            }
        }
    }

    QTimer::singleShot(retryDelayMs, this, [this]() { pumpUploads(); });
}
