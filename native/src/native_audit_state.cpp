#include "schgen/native_audit_state.hpp"
#include "schgen/occupancy.hpp"
#include "verification_internal.hpp"
#include <iomanip>

namespace schgen {
namespace {
const std::map<std::string,std::vector<std::string>> parents={
    {"netlist",{""}},{"link",{""}},{"floorplan.sizing",{"","docs.floorplan"}},
    {"sizing.pass",{"floorplan.sizing"}},{"pcb.placement",{""}},{"pcb.escape",{""}},
    {"pcb.emission",{""}},{"gates",{""}},{"docs.floorplan",{""}},{"census",{""}}};
std::string pad(const std::string& s,std::size_t width){return s+std::string(width>s.size()?width-s.size():0,' ');}
std::string shown(const JsonNode& v){
    if(v.kind==JsonKind::String)return v.string_value;
    if(v.kind==JsonKind::Bool)return v.bool_value?"yes":"no";
    if(v.kind!=JsonKind::Number)return verification::py_json_str(v);
    std::ostringstream s;s.imbue(std::locale::classic());s<<std::fixed<<std::setprecision(4)<<py_round(v.number_value,4);
    auto text=s.str();while(!text.empty()&&text.back()=='0')text.pop_back();if(!text.empty()&&text.back()=='.')text.pop_back();
    return text.empty()||text=="-0"?"0":text;
}
std::string tuple(const std::vector<std::string>& v){std::vector<std::string> q;for(const auto& s:v)q.push_back(model_checks::repr(s));return "("+model_checks::join(q,", ")+(v.size()==1?",":"")+")";}
}
NativeLedger::NativeLedger()=default;
void NativeLedger::declare(NativeLedgerDeclaration d){
    if(!entries_.empty()||!stack_.empty())throw std::logic_error("ledger: declarations are sealed during a build");
    if(d.name.empty()||std::any_of(declarations_.begin(),declarations_.end(),[&](const auto& x){return x.name==d.name;}))throw std::logic_error("ledger: duplicate or empty declaration "+model_checks::repr(d.name));
    if(!parents.count(d.step))throw std::logic_error("ledger: unknown step "+model_checks::repr(d.step));
    if(verification::utf8(d.basis).size()>88)throw std::logic_error("ledger: basis exceeds 88 characters");
    if(d.kind=="ASSUME"){
        static const std::set<std::string> classes={"physical","datasheet","standard","policy","fitted"};
        if(!classes.count(d.source)||d.covers.size()!=1||!d.resolve)throw std::logic_error("ledger: assumption needs a source class, one cover and live resolver");
    }else if(d.kind!="CALC"||d.inputs.empty()||d.expression.empty())throw std::logic_error("ledger: calculation needs named inputs and an expression");
    declarations_.push_back(std::move(d));
}
std::vector<NativeLedgerEntry>& NativeLedger::sink(){return shadow_.empty()?entries_:shadow_entries_;}
void NativeLedger::append(const std::string& kind,const std::string& name,const std::string& body){sink().push_back({kind,name,std::string(stack_.size()*2,' ')+pad(kind,6)+" "+body,stack_.size()});}
void NativeLedger::open_step(const std::string& name,const std::string& label){
    const auto p=parents.find(name);const auto here=stack_.empty()?"":stack_.back().first;
    if(p==parents.end())throw std::logic_error("ledger: undeclared step "+model_checks::repr(name));
    if(std::find(p->second.begin(),p->second.end(),here)==p->second.end())throw std::logic_error("ledger: step "+model_checks::repr(name)+" opened under wrong parent "+model_checks::repr(here));
    if(shadow_.empty()&&done_.count(name)&&name=="floorplan.sizing"){shadow_=name;shadow_entries_.clear();}
    append("STEP",name,name+(label.empty()?"":"  "+label));stack_.emplace_back(name,sink().size());
    for(const auto& d:declarations_)if(d.kind=="ASSUME"&&d.step==name){
        const auto value=shown(d.resolve());seen_.insert(d.name);
        append("ASSUME",d.name,pad(d.name,30)+" = "+pad(value,13)+" "+pad(d.unit,10)+" ["+d.source+"] "+d.covers.front()+" — "+d.basis);
    }
}
void NativeLedger::close_step(const std::string& name){
    if(stack_.empty()||stack_.back().first!=name)throw std::logic_error("ledger: close "+model_checks::repr(name)+" with mismatched stack");
    const auto start=stack_.back().second;stack_.pop_back();std::vector<std::pair<std::size_t,std::string>> body;
    for(std::size_t i=start;i<sink().size();++i){const auto& e=sink()[i];body.emplace_back(e.depth-stack_.size(),e.text.substr(e.text.find_first_not_of(' ')));}
    if(shadow_==name){
        const auto& first=done_.at(name);const bool same=first==body;shadow_.clear();shadow_entries_.clear();
        if(!same){std::size_t i=0;while(i<std::min(first.size(),body.size())&&first[i]==body[i])++i;
            const auto item=[](const auto& e){return "("+std::to_string(e.first)+", "+model_checks::repr(e.second)+")";};
            const auto diff=i<std::min(first.size(),body.size())?"line "+std::to_string(i)+": pass1 "+item(first[i])+" vs pass2 "+item(body[i]):"length "+std::to_string(first.size())+" vs "+std::to_string(body.size());
            problems_.push_back("replay of step "+model_checks::repr(name)+" diverged from its first pass — the doc pass and the shipped pass do not agree: "+diff);
        }
        append("REPLAY",name,name+" pass=2 identical="+(same?"yes":"NO")+" lines="+std::to_string(body.size()));
    }else done_.emplace(name,std::move(body));
}
void NativeLedger::calc(const std::string& name,const JsonNode& result,const std::vector<std::pair<std::string,JsonNode>>& inputs,const std::string& label){
    const auto p=std::find_if(declarations_.begin(),declarations_.end(),[&](const auto& d){return d.name==name;});
    if(p==declarations_.end()||p->kind!="CALC")throw std::logic_error("ledger: undeclared calculation "+model_checks::repr(name));
    const auto here=stack_.empty()?"":stack_.back().first;const auto& d=*p;
    if(here!=d.step)throw std::logic_error("ledger: calculation "+model_checks::repr(name)+" recorded under wrong step "+model_checks::repr(here));
    std::vector<std::string> keys,parts;for(const auto& [k,v]:inputs){keys.push_back(k);parts.push_back(k+"="+shown(v));}
    if(keys!=d.inputs)throw std::logic_error("ledger: calculation "+model_checks::repr(name)+" declares inputs "+tuple(d.inputs)+" but was recorded with "+tuple(keys)+" — inputs may not drift silently");
    if(seen_.count(name)&&!d.repeated&&shadow_.empty())problems_.push_back("calculation "+model_checks::repr(name)+" recorded more than once");
    seen_.insert(name);append("CALC",name,pad(name+(label.empty()?"":"["+label+"]"),30)+" = "+pad(shown(result),13)+" "+pad(d.unit,10)+" <- "+model_checks::join(parts," ")+"  ::  "+d.expression);
}
void NativeLedger::reset(){entries_.clear();shadow_entries_.clear();stack_.clear();done_.clear();seen_.clear();problems_.clear();shadow_.clear();}
LedgerAuditState NativeLedger::audit_state()const{
    LedgerAuditState s;for(const auto& d:declarations_)s.declarations.push_back({d.name,d.repeated,d.covers});s.recorded=seen_;s.n_lines=entries_.size();s.problems=problems_;
    for(const auto& e:stack_)s.problems.push_back("step "+model_checks::repr(e.first)+" was never closed");return s;
}
std::string NativeLedger::render()const{std::vector<std::string> rows;for(const auto& e:entries_)rows.push_back(e.text);return model_checks::join(rows);}
void NativeFallbacks::declare(NativeFallbackDeclaration d){std::lock_guard<std::mutex> guard(mutex_);
    if(d.name.empty()||d.stage.empty()||d.meaning.empty())throw std::logic_error("fallbacks: registration requires name, stage, meaning");
    const auto name=d.name;if(!declarations_.emplace(name,std::move(d)).second)throw std::logic_error("fallbacks: duplicate registration "+model_checks::repr(name));counts_[name]=0;
}
void NativeFallbacks::record(const std::string& name){std::lock_guard<std::mutex> guard(mutex_);if(!declarations_.count(name))throw std::logic_error("fallbacks: unregistered fallback "+model_checks::repr(name));if(counts_.at(name)==UINT64_MAX)throw std::overflow_error("fallbacks: event counter overflow");events_.push_back(name);++counts_.at(name);}
AuditCounts NativeFallbacks::census()const{std::lock_guard<std::mutex> guard(mutex_);AuditCounts out;for(const auto& [name,n]:counts_)out[name]=AuditInteger::decimal(std::to_string(n));return out;}
void NativeQuantizations::declare(NativeQuantizationDeclaration d){std::lock_guard<std::mutex> guard(mutex_);
    static const std::set<std::string> classes={"pre-proof","proof-preserving","re-validated"};
    if(d.name.empty()||d.symbol.empty()||d.value.empty()||d.basis.empty()||!d.evaluate||!classes.count(d.proof_class))throw std::logic_error("quantize: incomplete declaration or unknown proof class");
    for(const auto& [name,existing]:declarations_)if(existing.symbol==d.symbol)throw std::logic_error("quantize: duplicate implementation "+name);
    const auto name=d.name;if(!declarations_.emplace(name,std::move(d)).second)throw std::logic_error("quantize: duplicate registration "+model_checks::repr(name));counts_[name]=0;
}
double NativeQuantizations::invoke(const std::string& name,const std::vector<double>& args){
    std::function<double(const std::vector<double>&)> fn;
    {std::lock_guard<std::mutex> guard(mutex_);const auto p=declarations_.find(name);
        if(p==declarations_.end())throw std::logic_error("quantize: unregistered transform "+model_checks::repr(name));
        if(args.size()!=p->second.arity)throw std::invalid_argument("quantize: argument count mismatch for "+name);
        if(counts_.at(name)==UINT64_MAX)throw std::overflow_error("quantize: engagement counter overflow");
        ++counts_.at(name);fn=p->second.evaluate;
    }
    return fn(args); // never hold the counter mutex during user code; errors propagate
}
AuditCounts NativeQuantizations::engagements()const{std::lock_guard<std::mutex> guard(mutex_);AuditCounts out;for(const auto& [name,n]:counts_)out[name]=AuditInteger::decimal(std::to_string(n));return out;}
std::vector<NativeQuantizationDeclaration> NativeQuantizations::declarations()const{std::lock_guard<std::mutex> guard(mutex_);std::vector<NativeQuantizationDeclaration> out;for(const auto& [name,d]:declarations_){(void)name;out.push_back(d);}return out;}
} // namespace schgen
