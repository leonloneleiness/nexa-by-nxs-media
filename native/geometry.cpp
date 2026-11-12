// NEXA geometry ABI v1. No Python, Qt, or OS dependencies.
#include <algorithm>
#include <cmath>
#include <cstddef>
#ifdef _WIN32
#define API extern "C" __declspec(dllexport)
#else
#define API extern "C" __attribute__((visibility("default")))
#endif
struct V {
    double x,y,z;
    V operator+(V b) const { return {x+b.x,y+b.y,z+b.z}; }
    V operator-(V b) const { return {x-b.x,y-b.y,z-b.z}; }
    V operator*(double s) const { return {x*s,y*s,z*s}; }
};
static V get(const double* p) { return {p[0],p[1],p[2]}; }
static void put(double* p,V v) { p[0]=v.x;p[1]=v.y;p[2]=v.z; }
static double dot(V a,V b) {return a.x*b.x+a.y*b.y+a.z*b.z;}
static V cross(V a,V b) {return {a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x};}
static V unit(V a) {return a*(1.0/std::max(1e-12,std::sqrt(dot(a,a))));}
API int nexa_geometry_abi() {return 1;}
API int nexa_frames(const double* p,std::size_t count,const double* up,double* t,double* n,double* b) {
    if (!p || !up || !t || !n || !b || count<2) return 1;
    for(std::size_t i=0;i<count;i++) {
        V d=i==0 ? get(p+3)-get(p) : i==count-1 ? get(p+3*i)-get(p+3*(i-1)) : (get(p+3*(i+1))-get(p+3*(i-1)))*0.5;
        put(t+3*i,unit(d));
    }
    V t0=get(t), u=get(up), n0=u-t0*dot(u,t0);
    if (std::sqrt(dot(n0,n0))<1e-6) {
        V alt=std::abs(t0.x)<0.9 ? V{1,0,0} : V{0,1,0};
        n0=alt-t0*dot(alt,t0);
    }
    put(n,unit(n0));
    for(std::size_t i=0;i+1<count;i++) {
        V v1=get(p+3*(i+1))-get(p+3*i), ni=get(n+3*i);
        double c1=dot(v1,v1);
        if(c1<1e-18) {put(n+3*(i+1),ni);continue;}
        V r=ni-v1*((2/c1)*dot(v1,ni));
        V ti=get(t+3*i), tl=ti-v1*((2/c1)*dot(v1,ti));
        V v2=get(t+3*(i+1))-tl;
        double c2=dot(v2,v2);
        put(n+3*(i+1),unit(c2<1e-18 ? r : r-v2*((2/c2)*dot(v2,r))));
    }
    for(std::size_t i=0;i<count;i++) put(b+3*i,cross(get(t+3*i),get(n+3*i)));
    return 0;
}
