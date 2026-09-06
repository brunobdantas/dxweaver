#include "CtyResolver.h"

#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <fstream>
#include <sstream>

namespace dxw {

namespace {
char upperChar(char c) { return static_cast<char>(std::toupper(static_cast<unsigned char>(c))); }
}

std::string CtyResolver::trim(const std::string& value) {
    std::size_t first = 0;
    while (first < value.size() && std::isspace(static_cast<unsigned char>(value[first]))) ++first;
    std::size_t last = value.size();
    while (last > first && std::isspace(static_cast<unsigned char>(value[last - 1]))) --last;
    return value.substr(first, last - first);
}

std::string CtyResolver::upper(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), upperChar);
    return value;
}

std::vector<std::string> CtyResolver::split(const std::string& value, char separator) {
    std::vector<std::string> out;
    std::string current;
    for (std::size_t i = 0; i < value.size(); ++i) {
        if (value[i] == separator) {
            out.push_back(current);
            current.clear();
        } else {
            current.push_back(value[i]);
        }
    }
    out.push_back(current);
    return out;
}

bool CtyResolver::extractOverride(std::string& token, char open, char close, int& value) {
    const std::size_t a = token.find(open);
    if (a == std::string::npos) return false;
    const std::size_t b = token.find(close, a + 1);
    if (b == std::string::npos) return false;
    const std::string number = token.substr(a + 1, b - a - 1);
    if (number.empty()) return false;
    value = std::atoi(number.c_str());
    token.erase(a, b - a + 1);
    return true;
}

bool CtyResolver::longerKeyFirst(const Record& a, const Record& b) {
    if (a.exact != b.exact) return a.exact > b.exact;
    if (a.key.size() != b.key.size()) return a.key.size() > b.key.size();
    return a.key < b.key;
}

std::vector<std::string> CtyResolver::lookupForms(const std::string& callsign) {
    const std::string full = upper(trim(callsign));
    std::vector<std::string> forms;
    if (full.empty()) return forms;
    forms.push_back(full);
    const std::size_t slash = full.find('/');
    if (slash != std::string::npos) {
        const std::string left = full.substr(0, slash);
        const std::string right = full.substr(slash + 1);
        if (!left.empty()) forms.push_back(left);
        if (!right.empty() && right != "P" && right != "M" && right != "MM" &&
            right != "QRP" && right != "AM") forms.push_back(right);
    }
    return forms;
}

bool CtyResolver::load(const std::string& path) {
    records_.clear();
    std::ifstream in(path.c_str(), std::ios::in | std::ios::binary);
    if (!in) return false;

    std::string logical;
    std::string line;
    while (std::getline(in, line)) {
        logical += line;
        if (logical.empty() || logical[logical.size() - 1] != ';') continue;
        logical.erase(logical.size() - 1);
        const std::vector<std::string> fields = split(logical, ':');
        logical.clear();
        if (fields.size() < 8) continue;

        CtyEntity base;
        base.found = true;
        base.country = trim(fields[0]);
        base.cqZone = std::atoi(trim(fields[1]).c_str());
        base.ituZone = std::atoi(trim(fields[2]).c_str());
        base.continent = upper(trim(fields[3]));
        base.latitude = std::atof(trim(fields[4]).c_str());
        base.longitude = -std::atof(trim(fields[5]).c_str());

        std::string primary = upper(trim(fields[7]));
        primary.erase(std::remove(primary.begin(), primary.end(), '*'), primary.end());
        if (!primary.empty()) {
            Record rec;
            rec.key = primary;
            rec.entity = base;
            rec.entity.prefix = primary;
            records_.push_back(rec);
        }

        if (fields.size() >= 9) {
            const std::vector<std::string> aliases = split(fields[8], ',');
            for (std::size_t i = 0; i < aliases.size(); ++i) {
                std::string token = upper(trim(aliases[i]));
                if (token.empty()) continue;
                Record rec;
                rec.entity = base;
                if (token[0] == '=') {
                    rec.exact = true;
                    token.erase(0, 1);
                }
                extractOverride(token, '(', ')', rec.entity.cqZone);
                extractOverride(token, '[', ']', rec.entity.ituZone);
                const std::size_t braceA = token.find('{');
                const std::size_t braceB = token.find('}', braceA == std::string::npos ? 0 : braceA + 1);
                if (braceA != std::string::npos && braceB != std::string::npos) {
                    rec.entity.continent = token.substr(braceA + 1, braceB - braceA - 1);
                    token.erase(braceA, braceB - braceA + 1);
                }
                const std::size_t angleA = token.find('<');
                const std::size_t angleB = token.find('>', angleA == std::string::npos ? 0 : angleA + 1);
                if (angleA != std::string::npos && angleB != std::string::npos)
                    token.erase(angleA, angleB - angleA + 1);
                const std::size_t tildeA = token.find('~');
                if (tildeA != std::string::npos) {
                    const std::size_t tildeB = token.find('~', tildeA + 1);
                    if (tildeB != std::string::npos) token.erase(tildeA, tildeB - tildeA + 1);
                }
                token = trim(token);
                if (token.empty()) continue;
                rec.key = token;
                rec.entity.prefix = token;
                records_.push_back(rec);
            }
        }
    }
    std::stable_sort(records_.begin(), records_.end(), longerKeyFirst);
    return !records_.empty();
}

bool CtyResolver::resolve(const std::string& callsign, CtyEntity& result) const {
    result = CtyEntity();
    const std::vector<std::string> forms = lookupForms(callsign);
    for (std::size_t f = 0; f < forms.size(); ++f) {
        for (std::size_t i = 0; i < records_.size(); ++i) {
            const Record& rec = records_[i];
            if (rec.exact) {
                if (forms[f] == rec.key) {
                    result = rec.entity;
                    return true;
                }
            } else if (forms[f].size() >= rec.key.size() && forms[f].compare(0, rec.key.size(), rec.key) == 0) {
                result = rec.entity;
                return true;
            }
        }
    }
    return false;
}

} // namespace dxw
