.pragma library
function unit(p) { var n=Math.sqrt(p[0]*p[0]+p[1]*p[1]+p[2]*p[2]); return [p[0]/n,p[1]/n,p[2]/n] }
function create() {
    var g=(1+Math.sqrt(5))/2;
    var v=[[-1,g,0],[1,g,0],[-1,-g,0],[1,-g,0],[0,-1,g],[0,1,g],[0,-1,-g],[0,1,-g],[g,0,-1],[g,0,1],[-g,0,-1],[-g,0,1]].map(unit);
    var f=[[0,11,5],[0,5,1],[0,1,7],[0,7,10],[0,10,11],[1,5,9],[5,11,4],[11,10,2],[10,7,6],[7,1,8],[3,9,4],[3,4,2],[3,2,6],[3,6,8],[3,8,9],[4,9,5],[2,4,11],[6,2,10],[8,6,7],[9,8,1]];
    for(var d=0;d<3;d++) {
        var cache={}, next=[];
        function mid(a,b) { var key=Math.min(a,b)+":"+Math.max(a,b); if(cache[key]!==undefined)return cache[key]; var p=v[a],q=v[b]; v.push(unit([p[0]+q[0],p[1]+q[1],p[2]+q[2]])); return cache[key]=v.length-1 }
        for(var i=0;i<f.length;i++) { var t=f[i],a=mid(t[0],t[1]),b=mid(t[1],t[2]),c=mid(t[2],t[0]); next.push([t[0],a,c],[t[1],b,a],[t[2],c,b],[a,b,c]); }
        f=next;
    }
    return {vertices:v, faces:f};
}
var mesh=create();

// Each independent shard retains its own center and local triangle, never shared edges.
function makeShards() {
    var shards=[];
    for(var i=0;i<mesh.faces.length;i+=2) {
        var f=mesh.faces[i], a=mesh.vertices[f[0]], b=mesh.vertices[f[1]], c=mesh.vertices[f[2]];
        var center=[(a[0]+b[0]+c[0])/3,(a[1]+b[1]+c[1])/3,(a[2]+b[2]+c[2])/3];
        var local=[a,b,c].map(function(p){return [(p[0]-center[0])*0.72,(p[1]-center[1])*0.72,(p[2]-center[2])*0.72]});
        shards.push({center:center,local:local,seed:i*2.3999632297});
    }
    return shards;
}
var shards=makeShards();
