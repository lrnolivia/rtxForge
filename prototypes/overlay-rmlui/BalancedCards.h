#pragma once
#include <RmlUi/Core.h>
#include <algorithm>
#include <array>
#include <map>
#include <string>
#include <vector>

namespace ForgeGlass {
// Independent vertical stacks keep a short card from reserving a whole grid row.
// Repack only when the breakpoint or an accordion changes, never from animated bounds.
struct BalancedCards {
    std::map<Rml::Element*, std::string> signatures;
    void Arrange(Rml::Element* host, bool wide) {
        if (!host || !host->IsVisible()) return;
        std::vector<Rml::Element*> cards;
        for (int i=0; i<host->GetNumChildren(); ++i) {
            auto* child=host->GetChild(i);
            if (child->IsClassSet("mosaic-column")) {
                for (int j=0; j<child->GetNumChildren(); ++j) cards.push_back(child->GetChild(j));
            } else if (child->IsClassSet("option-group") || child->IsClassSet("settings-group")) cards.push_back(child);
        }
        if (cards.empty()) return;
        for (size_t i=0; i<cards.size(); ++i) if (!cards[i]->HasAttribute("data-mosaic-order")) cards[i]->SetAttribute("data-mosaic-order",int(i));
        std::stable_sort(cards.begin(),cards.end(),[](auto* a,auto* b){return a->template GetAttribute<int>("data-mosaic-order",0)<b->template GetAttribute<int>("data-mosaic-order",0);});
        std::string signature=wide?"wide":"stack";
        std::vector<float> weights;
        for (auto* card:cards) {
            Rml::ElementList controls;card->QuerySelectorAll(controls,"input, select, .switch, .settings-layouts, .shortcut-bind");
            float weight=1;
            auto* body=card->QuerySelector(".group-body");
            if(!body || body->IsVisible()) for(auto* control:controls) weight+=control->IsClassSet("settings-layouts")?2.5f:1.f;
            weights.push_back(weight);
            signature+="/"+std::to_string(reinterpret_cast<uintptr_t>(card))+":"+std::to_string(weight);
        }
        if(signatures[host]==signature) return;
        signatures[host]=signature;
        std::vector<Rml::ElementPtr> detached;
        for(auto* card:cards) detached.push_back(card->GetParentNode()->RemoveChild(card));
        for(int i=host->GetNumChildren()-1;i>=0;--i) if(host->GetChild(i)->IsClassSet("mosaic-column")) host->RemoveChild(host->GetChild(i));
        host->SetClass("mosaic",wide);
        auto* trailing=host->GetChild(0);
        if(!wide) { for(auto& card:detached) host->InsertBefore(std::move(card),trailing);return; }
        std::array<Rml::Element*,2> columns{};
        for(auto& column:columns) {auto node=host->GetOwnerDocument()->CreateElement("div");node->SetClass("mosaic-column",true);column=host->InsertBefore(std::move(node),trailing);}
        std::vector<size_t> order(cards.size());for(size_t i=0;i<order.size();++i)order[i]=i;
        std::stable_sort(order.begin(),order.end(),[&](size_t a,size_t b){return weights[a]>weights[b];});
        std::array<float,2> totals{};std::vector<int> destinations(cards.size());
        // Put a dominant tall card on the right, leaving room for the shorter stack.
        for(auto index:order){const int column=totals[0]==totals[1]?(index==0?0:1):(totals[0]<totals[1]?0:1);destinations[index]=column;totals[column]+=weights[index];}
        for(size_t i=0;i<detached.size();++i) columns[destinations[i]]->AppendChild(std::move(detached[i]));
    }
};
}
