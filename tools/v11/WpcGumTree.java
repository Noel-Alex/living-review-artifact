import java.io.*;
import java.util.*;
import com.github.gumtreediff.client.Run;
import com.github.gumtreediff.gen.TreeGenerators;
import com.github.gumtreediff.tree.Tree;
import com.github.gumtreediff.matchers.*;
import com.github.gumtreediff.actions.*;
import com.github.gumtreediff.actions.model.*;
import org.treesitter.*;
import java.nio.file.*;

/** Persistent official-library bridge. Input: old path TAB new path TAB generator. */
public class WpcGumTree {
    static List<Tree> nodes(Tree t) {
        List<Tree> r=new ArrayList<>();
        for(Tree n:t.preOrder()) {
            if(n.getType().name.equals("ERROR") || n.getType().name.equals("MISSING"))
                throw new IllegalArgumentException("parse recovery node: "+n.getType().name);
            r.add(n);
        }
        return r;
    }
    static IdentityHashMap<Tree,Integer> ids(List<Tree> ns) {
        IdentityHashMap<Tree,Integer> m=new IdentityHashMap<>();
        for(int i=0;i<ns.size();i++)m.put(ns.get(i),i);
        return m;
    }
    static int hybrid(List<String> lines,TSPoint p) {
        int offset=p.getColumn();for(int i=0;i<p.getRow();i++)offset+=lines.get(i).length()+1;return offset;
    }
    static Map<String,int[]> sourceLines(String path,String generator)throws Exception {
        String language=switch(generator.split("-")[0]) {
            case "python"->"Python";case "java"->"Java";case "js"->"Javascript";
            case "cs"->"CSharp";case "cpp"->"Cpp";case "go"->"Go";case "ruby"->"Ruby";
            case "ts"->"Typescript";case "tsx"->"Tsx";case "php"->"Php";
            default->throw new IllegalArgumentException(generator);
        };
        TSLanguage l=(TSLanguage)Class.forName("org.treesitter.TreeSitter"+language).getConstructor().newInstance();
        String text=Files.readString(Path.of(path));List<String> lines=Arrays.asList(text.split("\n",-1));
        Map<String,int[]> result=new HashMap<>();
        try(TSParser parser=new TSParser()) {
            parser.setLanguage(l);TSTree tree=parser.parseString(null,text);
            if(tree.getRootNode().hasError())throw new IllegalArgumentException("tree-sitter syntax/recovery error");
            Deque<TSNode> stack=new ArrayDeque<>();stack.push(tree.getRootNode());
            while(!stack.isEmpty()) {
                TSNode n=stack.pop();
                if(n.isMissing())throw new IllegalArgumentException("tree-sitter missing node");
                int s=hybrid(lines,n.getStartPoint()),e=hybrid(lines,n.getEndPoint());
                int sl=n.getStartPoint().getRow()+1,el=n.getEndPoint().getRow()+1;
                if(n.getEndPoint().getColumn()==0 && el>sl)el--;
                result.put(s+":"+(e-s),new int[]{sl,el});
                for(int i=0;i<n.getChildCount();i++)stack.push(n.getChild(i));
            }
        }
        return result;
    }
    static String dump(List<Tree> ns,IdentityHashMap<Tree,Integer> ids,Map<String,int[]> lines) {
        StringJoiner s=new StringJoiner(",","[","]");
        for(Tree n:ns) {
            int[] loc=lines.get(n.getPos()+":"+n.getLength());
            if(loc==null && n.getLength()>0)throw new IllegalStateException("source extent not found");
            if(loc==null)loc=new int[]{1,1};
            s.add("["+ids.get(n)+","+ids.getOrDefault(n.getParent(),-1)+","+n.getPos()+","+n.getLength()+","+loc[0]+","+loc[1]+"]");
        }
        return s.toString();
    }
    public static void main(String[] args)throws Exception {
        Run.initGenerators();Run.initMatchers();
        BufferedReader input=new BufferedReader(new InputStreamReader(System.in,java.nio.charset.StandardCharsets.UTF_8));
        String line;
        while((line=input.readLine())!=null) {
            long begin=System.nanoTime();
            try {
                String[] a=line.split("\t",-1);
                Tree old=TreeGenerators.getInstance().getTree(a[0],a[2]).getRoot();
                Tree neo=TreeGenerators.getInstance().getTree(a[1],a[2]).getRoot();
                var oldLines=sourceLines(a[0],a[2]);var newLines=sourceLines(a[1],a[2]);
                List<Tree> os=nodes(old),ns=nodes(neo);
                var oi=ids(os);var ni=ids(ns);
                var matcher=Matchers.getInstance().getMatcher();
                MappingStore mappings=matcher.match(old,neo);
                StringJoiner matches=new StringJoiner(",","[","]");
                for(Mapping m:mappings)matches.add("["+oi.get(m.first)+","+ni.get(m.second)+"]");
                StringJoiner actions=new StringJoiner(",","[","]");
                for(Action act:new SimplifiedChawatheScriptGenerator().computeActions(mappings)) {
                    boolean insert=act.getName().startsWith("insert");
                    var map=insert?ni:oi;
                    Integer id=map.get(act.getNode());
                    if(id==null)throw new IllegalStateException("action node missing: "+act.getName());
                    actions.add("[\""+act.getName()+"\","+(insert?1:0)+","+id+"]");
                }
                System.out.println("{\"old\":"+dump(os,oi,oldLines)+",\"new\":"+dump(ns,ni,newLines)+",\"matches\":"+matches+",\"actions\":"+actions+",\"matcher\":\""+matcher.getClass().getName()+"\",\"ms\":"+(System.nanoTime()-begin)/1e6+"}");
            }catch(Throwable t) {
                t.printStackTrace(System.err);
                String msg=t.toString().replace("\\","\\\\").replace("\"","\\\"").replace("\n"," ").replace("\r"," ");
                System.out.println("{\"error\":\""+msg+"\"}");
            }
            System.out.flush();
        }
    }
}
